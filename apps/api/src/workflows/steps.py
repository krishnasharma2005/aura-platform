"""Step shapes, placeholder rendering, and the condition registry.

A workflow definition is data in the database, which means the step list is
attacker-adjacent in exactly the way a model's tool call is: it must not be
able to express "run this arbitrary code". So a step never carries logic — it
carries a *name from a fixed registry* plus parameters. Branch conditions are
looked up in `CHECKS` below; anything not in the registry is a definition
error, not an eval().

Step types
----------
    {"id": "read_diary", "name": "Read tomorrow's appointments",
     "type": "tool", "tool": "calendar", "as_agent": "receptionist",
     "arguments": {"action": "list_events"}}

    {"id": "draft", "name": "Write the reminder", "type": "agent",
     "agent": "receptionist", "prompt": "...", "conversation_key": "..."}

    {"id": "hold", "name": "Wait until after the appointment",
     "type": "wait", "minutes": 1440}

    {"id": "gate", "name": "Did they confirm?", "type": "branch",
     "check": "conversation_unanswered", "params": {"minutes": 0},
     "on_false": "stop"}

    {"id": "tell_sarah", "name": "Flag it for a human", "type": "escalate",
     "reason": "A website enquiry has gone {{minutes}} minutes without a reply."}

Common optional keys: `optional: true` means a failure is recorded but does not
fail the run (used for the AI drafting step in the escalation template — losing
the summary must not lose the escalation).

Placeholders
------------
`{{some.path}}` in any string is replaced from the run context. A missing path
renders as an empty string rather than raising: a half-populated context should
degrade to a vaguer message, not a wedged run.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.conversations.models import Contact, Conversation, Message

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.\- ']+?)\s*\}\}")


class WorkflowDefinitionError(Exception):
    """A stored definition asks for something the engine doesn't know how to
    do. Surfaced as a failed step with a plain-language detail."""


# --------------------------------------------------------------------------
# Context lookup + rendering
# --------------------------------------------------------------------------


def resolve_path(context: dict[str, Any], path: str) -> Any:
    """Walks a dotted path through nested dicts/lists. Returns None if any
    segment is missing — see the module docstring on why this is not an error."""
    current: Any = context
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            current = current[index] if index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def render(value: Any, context: dict[str, Any]) -> Any:
    """Renders placeholders through a string, or recursively through a
    dict/list of them. Non-string leaves pass through untouched."""
    if isinstance(value, str):
        def _sub(match: re.Match[str]) -> str:
            resolved = resolve_path(context, match.group(1))
            return "" if resolved is None else str(resolved)

        return _PLACEHOLDER.sub(_sub, value)
    if isinstance(value, dict):
        return {key: render(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, context) for item in value]
    return value


# --------------------------------------------------------------------------
# Branch conditions
# --------------------------------------------------------------------------


class CheckResult:
    """`passed` decides the branch; `data` is merged into the step's context
    entry so later steps can use what the check found (the recall template's
    "who is due" list arrives this way)."""

    def __init__(self, passed: bool, detail: str, data: dict[str, Any] | None = None) -> None:
        self.passed = passed
        self.detail = detail
        self.data = data or {}


def _now() -> datetime:
    # Naive UTC, matching every other timestamp column in the schema.
    return datetime.now(UTC).replace(tzinfo=None)


async def check_always(db: AsyncSession, org_id: uuid.UUID, context: dict[str, Any], params: dict[str, Any]) -> CheckResult:
    return CheckResult(True, "Continuing.")


async def check_context_not_empty(
    db: AsyncSession, org_id: uuid.UUID, context: dict[str, Any], params: dict[str, Any]
) -> CheckResult:
    """True when a list the previous step produced has anything in it — e.g.
    "are there actually appointments tomorrow?"."""
    path = params.get("path", "")
    value = resolve_path(context, path)
    count = len(value) if isinstance(value, (list, dict, str)) else (0 if value is None else 1)
    if count:
        return CheckResult(True, f"Found {count} to work through.", {"count": count})
    return CheckResult(False, "Nothing to do this time.", {"count": 0})


async def check_conversation_unanswered(
    db: AsyncSession, org_id: uuid.UUID, context: dict[str, Any], params: dict[str, Any]
) -> CheckResult:
    """True when the newest message on the conversation came from the customer
    and has been sitting there longer than `minutes`.

    This is the load-bearing condition in two of the three templates: it is how
    "the enquiry went unanswered" and "they never replied to the reminder" are
    detected without any integration being connected.
    """
    key = params.get("conversation_key") or context.get("conversation_key")
    if not key:
        return CheckResult(False, "No conversation to check.")

    conversation = (
        await db.execute(
            select(Conversation).where(Conversation.org_id == org_id, Conversation.key == str(key))
        )
    ).scalar_one_or_none()
    if conversation is None:
        return CheckResult(False, "That conversation no longer exists.")

    last = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is None:
        return CheckResult(False, "That conversation has no messages.")

    if last.role != "user":
        return CheckResult(False, "It's already been answered.")

    threshold = int(params.get("minutes", 0))
    waited = _now() - last.created_at
    if waited < timedelta(minutes=threshold):
        return CheckResult(False, "It hasn't been waiting long enough yet.")

    return CheckResult(
        True,
        f"Still waiting for a reply after {int(waited.total_seconds() // 60)} minutes.",
        {"minutes_waiting": int(waited.total_seconds() // 60)},
    )


async def check_contacts_due_for_recall(
    db: AsyncSession, org_id: uuid.UUID, context: dict[str, Any], params: dict[str, Any]
) -> CheckResult:
    """True when anyone hasn't been seen for `days`. The recall interval is the
    configurable part of the recall template — 12 weeks for a hygiene visit,
    16 for filler, whatever the clinic actually runs."""
    days = int(params.get("days", 90))
    limit = int(params.get("limit", 25))
    cutoff = _now() - timedelta(days=days)

    rows = list(
        (
            await db.execute(
                select(Contact)
                .where(Contact.org_id == org_id, Contact.last_seen_at <= cutoff)
                .order_by(Contact.last_seen_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    people = [
        {"id": str(row.id), "name": row.name, "phone": row.phone, "email": row.email}
        for row in rows
    ]
    if not people:
        return CheckResult(False, f"Nobody is due a follow-up after {days} days.", {"contacts": [], "count": 0})
    names = ", ".join(person["name"] or "a patient" for person in people[:5])
    return CheckResult(
        True,
        f"{len(people)} due a follow-up after {days} days: {names}"
        + ("…" if len(people) > 5 else ""),
        {"contacts": people, "count": len(people), "names": names},
    )


CHECKS = {
    "always": check_always,
    "context_not_empty": check_context_not_empty,
    "conversation_unanswered": check_conversation_unanswered,
    "contacts_due_for_recall": check_contacts_due_for_recall,
}


async def run_check(
    name: str, db: AsyncSession, org_id: uuid.UUID, context: dict[str, Any], params: dict[str, Any]
) -> CheckResult:
    check = CHECKS.get(name)
    if check is None:
        raise WorkflowDefinitionError(f"This workflow asks for a condition we don't recognise: '{name}'.")
    return await check(db, org_id, context, params)
