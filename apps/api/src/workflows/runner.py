"""The scheduled runner, and the event-bus bridge.

**Deliberately not Celery.** There is no broker, no worker fleet and no beat
process. At this scale (tens of organizations, a handful of scheduled
workflows each, one tick every 30 seconds) a broker is three more things to
deploy, monitor and get paged about, in exchange for nothing we need. The
runner is an `asyncio` task started in the FastAPI lifespan; it shares the
process and the connection pool with the API.

**Running more than one instance is safe.** Every unit of work — a due
definition, a run ready to resume — is taken with a conditional UPDATE that
advances the schedule in the same statement (`service.claim_due_*`). Two
instances ticking at the same instant produce exactly one claim; the loser
matches zero rows and moves on. That is the whole locking story, and it needs
nothing from the database beyond `UPDATE ... WHERE`.

**Cron instead, if you'd rather.** `python -m scripts.run_workflows --once`
runs a single tick and exits, for anyone who wants the schedule owned by cron
or a Kubernetes CronJob rather than by the app process. Set
`WORKFLOWS_RUNNER_ENABLED=false` so the in-process loop doesn't also run. The
locking makes mixing the two harmless anyway.
"""

import asyncio
import contextlib
import uuid
from typing import Any

from src.ai_gateway.gateway import AIGateway
from src.core.config import get_settings
from src.core.db import async_session_factory
from src.core.logging import get_logger
from src.events.bus import event_bus
from src.workflows import engine, service

logger = get_logger(__name__)

# Identifies this process in `locked_by`. Useful when a lock goes stale and
# somebody needs to know which instance died holding it.
WORKER_ID = uuid.uuid4().hex[:16]

_task: asyncio.Task | None = None


async def tick() -> dict[str, int]:
    """One pass: start anything scheduled that is due, then advance every run
    that is ready to move. Returns counts, which is what makes it testable and
    what the management command prints."""
    settings = get_settings()
    lock_timeout = int(getattr(settings, "WORKFLOW_LOCK_TIMEOUT_SECONDS", 600))
    started = 0
    advanced = 0

    async with async_session_factory() as db:
        for definition in await service.claim_due_definitions(db, WORKER_ID, lock_timeout):
            try:
                await engine.start_run(db, definition, trigger_source="schedule")
                started += 1
            except Exception as exc:  # pragma: no cover - a bad definition must not stop the tick
                logger.error(
                    "workflow_schedule_failed",
                    exc_info=exc,
                    extra={"extra_fields": {"workflow": definition.slug}},
                )
            finally:
                await service.release_definition(db, definition)

        gateway = AIGateway() if settings.OPENAI_API_KEY else None
        for run in await service.claim_due_runs(db, WORKER_ID, lock_timeout):
            try:
                definition = await service.get_definition(db, run.org_id, run.workflow_id)
                await engine.execute_run(db, run, definition, gateway=gateway)
                advanced += 1
            except Exception as exc:  # pragma: no cover
                logger.error(
                    "workflow_run_failed", exc_info=exc, extra={"extra_fields": {"run_id": str(run.id)}}
                )
            finally:
                await service.release_run(db, run)

    return {"started": started, "advanced": advanced}


async def _loop(interval_seconds: int) -> None:
    logger.info("workflow_runner_started", extra={"extra_fields": {"worker": WORKER_ID}})
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - the loop must outlive any single failure
            logger.error("workflow_tick_failed", exc_info=exc)
        await asyncio.sleep(interval_seconds)


def start() -> None:
    global _task
    settings = get_settings()
    if not getattr(settings, "WORKFLOWS_RUNNER_ENABLED", True):
        logger.info("workflow_runner_disabled")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop(int(getattr(settings, "WORKFLOW_TICK_SECONDS", 30))))


async def stop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _task
    _task = None


# --------------------------------------------------------------------------
# Event triggers
# --------------------------------------------------------------------------


async def handle_event(event_name: str, payload: dict[str, Any]) -> None:
    """Creates a run for every enabled event-triggered workflow in the payload's
    organization. It only *creates* — a customer's message must never wait on a
    workflow, so execution happens on the next tick."""
    org_id = payload.get("org_id")
    if org_id is None:
        return

    async with async_session_factory() as db:
        definitions = await service.find_event_definitions(db, org_id, event_name)
        for definition in definitions:
            if not service.event_filter_matches(definition, payload):
                continue
            await engine.start_run(
                db,
                definition,
                trigger_source="event",
                context={
                    "event": event_name,
                    "conversation_key": payload.get("conversation_key"),
                    "channel": payload.get("channel"),
                    "contact_phone": payload.get("contact_phone"),
                    "contact_name": payload.get("contact_name"),
                    "last_message": payload.get("last_message"),
                },
            )


# Event names an event-triggered workflow may subscribe to. Kept as an
# allowlist rather than "whatever string is in trigger_config" so a stored
# definition cannot make the engine listen to something that was never meant
# to be a trigger.
TRIGGERABLE_EVENTS = ("conversation.message_received",)

_triggers_registered = False


def register_event_triggers() -> None:
    """Idempotent: `create_app()` is called more than once in the test suite,
    and subscribing twice would start two runs for one customer message."""
    global _triggers_registered
    if _triggers_registered:
        return
    for event_name in TRIGGERABLE_EVENTS:
        event_bus.subscribe(
            event_name,
            lambda payload, _name=event_name: handle_event(_name, payload),
        )
    _triggers_registered = True
