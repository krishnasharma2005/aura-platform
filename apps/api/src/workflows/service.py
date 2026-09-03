"""Org-scoped reads/writes for workflows, plus the claim/lock primitives the
scheduler is built on.

Every lookup takes an `org_id` and filters on it. A workflow or run id from one
tenant must never resolve in another, so there is no `get_by_id(id)` anywhere in
this module — only `get_definition(db, org_id, workflow_id)`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.workflows.models import (
    RunStatus,
    TriggerType,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStepRun,
)
from src.workflows.templates import TEMPLATES


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --------------------------------------------------------------------------
# Definitions
# --------------------------------------------------------------------------


async def seed_templates(
    db: AsyncSession, org_id: uuid.UUID, enable: list[str] | None = None
) -> list[WorkflowDefinition]:
    """Installs the pre-built templates for an organization. Idempotent: an
    existing row keeps its `enabled` flag and its counters, but has its
    name/description/steps refreshed so a template improvement reaches every
    customer without a data migration.

    `enable` names the slugs that should be switched on (defaults to none —
    an automation that starts messaging customers the moment an org is created
    is not a decision we get to make for them).
    """
    enable = enable or []
    definitions: list[WorkflowDefinition] = []

    for template in TEMPLATES:
        existing = (
            await db.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.org_id == org_id,
                    WorkflowDefinition.slug == template["slug"],
                )
            )
        ).scalar_one_or_none()

        definition = existing or WorkflowDefinition(org_id=org_id, slug=template["slug"])
        definition.name = template["name"]
        definition.description = template["description"]
        definition.trigger_type = template["trigger_type"]
        definition.trigger_config = template["trigger_config"]
        definition.steps = template["steps"]
        definition.updated_at = _now()
        if existing is None:
            definition.enabled = template["slug"] in enable
            db.add(definition)
        elif template["slug"] in enable:
            definition.enabled = True

        if definition.enabled and definition.trigger_type is TriggerType.schedule:
            definition.next_run_at = definition.next_run_at or _next_run_from(definition, _now())
        definitions.append(definition)

    await db.commit()
    for definition in definitions:
        await db.refresh(definition)
    return definitions


def _interval_minutes(definition: WorkflowDefinition) -> int:
    config = definition.trigger_config or {}
    return max(1, int(config.get("interval_minutes") or 60 * 24))


def _next_run_from(definition: WorkflowDefinition, moment: datetime) -> datetime:
    return moment + timedelta(minutes=_interval_minutes(definition))


async def list_definitions(db: AsyncSession, org_id: uuid.UUID) -> list[WorkflowDefinition]:
    stmt = (
        select(WorkflowDefinition)
        .where(WorkflowDefinition.org_id == org_id)
        .order_by(WorkflowDefinition.created_at.asc(), WorkflowDefinition.name.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_definition(
    db: AsyncSession, org_id: uuid.UUID, workflow_id: uuid.UUID
) -> WorkflowDefinition:
    definition = (
        await db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == workflow_id, WorkflowDefinition.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if definition is None:
        raise NotFoundError("We couldn't find that automation.")
    return definition


async def set_enabled(
    db: AsyncSession, org_id: uuid.UUID, workflow_id: uuid.UUID, enabled: bool
) -> WorkflowDefinition:
    definition = await get_definition(db, org_id, workflow_id)
    definition.enabled = enabled
    definition.updated_at = _now()
    if enabled and definition.trigger_type is TriggerType.schedule:
        # Turning it on schedules the first run one interval out, not
        # immediately — nobody wants "enable" to mean "message 25 patients now".
        definition.next_run_at = _next_run_from(definition, _now())
    elif not enabled:
        definition.next_run_at = None
    await db.commit()
    await db.refresh(definition)
    return definition


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------


async def list_runs(
    db: AsyncSession, org_id: uuid.UUID, workflow_id: uuid.UUID, limit: int = 20
) -> list[WorkflowRun]:
    await get_definition(db, org_id, workflow_id)  # 404s across tenants
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.org_id == org_id, WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.started_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_step_runs(db: AsyncSession, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[WorkflowStepRun]]:
    if not run_ids:
        return {}
    rows = list(
        (
            await db.execute(
                select(WorkflowStepRun)
                .where(WorkflowStepRun.run_id.in_(run_ids))
                .order_by(WorkflowStepRun.run_id, WorkflowStepRun.position)
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[uuid.UUID, list[WorkflowStepRun]] = {run_id: [] for run_id in run_ids}
    for row in rows:
        grouped.setdefault(row.run_id, []).append(row)
    return grouped


# --------------------------------------------------------------------------
# Claiming — the reason two API instances don't double-fire
# --------------------------------------------------------------------------
#
# There is no broker and no Celery here (see docs: the runner is an asyncio
# task in the app lifespan). Safety comes from the database instead. Claiming
# is a conditional UPDATE that *also* advances `next_run_at` in the same
# statement, so a second worker racing on the same row matches zero rows and
# walks away. Nothing depends on statement ordering, row locks, or clock
# agreement between instances beyond a few seconds.
#
# A worker that dies mid-run leaves a stale lock. `lock_timeout_seconds`
# bounds how long that work is stranded.


async def claim_due_definitions(
    db: AsyncSession, worker_id: str, lock_timeout_seconds: int, limit: int = 20
) -> list[WorkflowDefinition]:
    now = _now()
    stale_before = now - timedelta(seconds=lock_timeout_seconds)

    candidates = list(
        (
            await db.execute(
                select(WorkflowDefinition)
                .where(
                    WorkflowDefinition.enabled.is_(True),
                    WorkflowDefinition.trigger_type == TriggerType.schedule,
                    WorkflowDefinition.next_run_at.is_not(None),
                    WorkflowDefinition.next_run_at <= now,
                )
                .order_by(WorkflowDefinition.next_run_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    claimed: list[WorkflowDefinition] = []
    for candidate in candidates:
        result = await db.execute(
            update(WorkflowDefinition)
            .where(
                WorkflowDefinition.id == candidate.id,
                WorkflowDefinition.next_run_at.is_not(None),
                WorkflowDefinition.next_run_at <= now,
                (WorkflowDefinition.locked_at.is_(None))
                | (WorkflowDefinition.locked_at < stale_before),
            )
            .values(
                locked_at=now,
                locked_by=worker_id,
                next_run_at=now + timedelta(minutes=_interval_minutes(candidate)),
            )
        )
        await db.commit()
        if result.rowcount == 1:
            await db.refresh(candidate)
            claimed.append(candidate)
    return claimed


async def release_definition(db: AsyncSession, definition: WorkflowDefinition) -> None:
    definition.locked_at = None
    definition.locked_by = None
    await db.commit()


async def claim_due_runs(
    db: AsyncSession, worker_id: str, lock_timeout_seconds: int, limit: int = 50
) -> list[WorkflowRun]:
    """Runs that are mid-flight and due to move on — the ones parked on a wait
    step, plus the ones an event handler created and left for us."""
    now = _now()
    stale_before = now - timedelta(seconds=lock_timeout_seconds)

    candidates = list(
        (
            await db.execute(
                select(WorkflowRun)
                .where(
                    WorkflowRun.status == RunStatus.running,
                    WorkflowRun.resume_at.is_not(None),
                    WorkflowRun.resume_at <= now,
                )
                .order_by(WorkflowRun.resume_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    claimed: list[WorkflowRun] = []
    for candidate in candidates:
        result = await db.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == candidate.id,
                WorkflowRun.status == RunStatus.running,
                WorkflowRun.resume_at.is_not(None),
                WorkflowRun.resume_at <= now,
                (WorkflowRun.locked_at.is_(None)) | (WorkflowRun.locked_at < stale_before),
            )
            # resume_at is cleared as part of the claim so a second worker
            # cannot pick the same run up while this one is executing it.
            .values(locked_at=now, locked_by=worker_id, resume_at=None)
        )
        await db.commit()
        if result.rowcount == 1:
            await db.refresh(candidate)
            claimed.append(candidate)
    return claimed


async def release_run(db: AsyncSession, run: WorkflowRun) -> None:
    run.locked_at = None
    run.locked_by = None
    await db.commit()


async def find_event_definitions(
    db: AsyncSession, org_id: uuid.UUID, event_name: str
) -> list[WorkflowDefinition]:
    stmt = select(WorkflowDefinition).where(
        WorkflowDefinition.org_id == org_id,
        WorkflowDefinition.enabled.is_(True),
        WorkflowDefinition.trigger_type == TriggerType.event,
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return [row for row in rows if (row.trigger_config or {}).get("event") == event_name]


def event_filter_matches(definition: WorkflowDefinition, payload: dict[str, Any]) -> bool:
    """Channel filter for event triggers. An empty/absent `channels` list means
    "any channel"."""
    channels = (definition.trigger_config or {}).get("channels")
    if not channels:
        return True
    return payload.get("channel") in channels
