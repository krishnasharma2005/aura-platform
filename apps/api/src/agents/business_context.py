"""Per-organization structured business profile — the customer's own business
identity, offerings, customer profile, brand voice, policies, and operating
procedures, used to ground every agent in facts about *this* business instead
of a generic one.

Ported from dist/mesnium-business/context-store.js + types.js in the
openclaw/claw fork. Deliberately separate from — and unrelated to —
organizations.business_type/primary_goal (identity/models.py): those two
columns are a single onboarding-form answer never read by the agent runtime
today (confirmed: no code path injects them into a prompt). This is the real
thing they were meant to become. They are left untouched here rather than
migrated, since removing them would require coordinating a frontend
onboarding-form change alongside this backend work — tracked as a follow-up,
not done silently.

One row per organization, seven JSON sections mirroring Mesnium's structure:
  identity   — business name, industry, description, location, hours, timezone
  offerings  — services/products offered, pricing notes
  customers  — target customer description, qualification criteria
  brand      — tone of voice, communication style
  policies   — things agents may/must-not say, escalation & approval rules
  operations — standard operating procedures, priorities
  contacts   — owners, staff, escalation contacts

A new organization gets an empty context lazily on first read — no assumed
defaults, no Mesnium-branded placeholder text carried over from the source
this was ported from. Turning that into agent-visible text happens in
agents/runtime/context_projector.py, not here: this module only stores and
validates the data.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.db import Base
from src.core.exceptions import ValidationError

_SECTIONS = ("identity", "offerings", "customers", "brand", "policies", "operations", "contacts")

# Mirrors Mesnium's MAX_LIMITS: this endpoint's input comes directly from an
# org owner's form submission, a real trust boundary, so it's worth capping
# even though nothing downstream would crash without it.
_MAX_STRING_LENGTH = 1000
_MAX_ARRAY_ITEMS = 50
_MAX_OBJECT_DEPTH = 6


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class BusinessContext(Base):
    """One organization's business profile. Absence of a row means "never
    set" — get_context() below creates and persists an empty one on first
    read so callers never have to special-case None."""

    __tablename__ = "business_contexts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True, index=True)
    identity: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    offerings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    customers: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    brand: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    policies: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    operations: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    contacts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


@dataclass
class BusinessContextPatch:
    """A partial update: only sections present are validated and merged;
    omitted sections are left exactly as they were."""

    identity: dict[str, Any] | None = None
    offerings: dict[str, Any] | None = None
    customers: dict[str, Any] | None = None
    brand: dict[str, Any] | None = None
    policies: dict[str, Any] | None = None
    operations: dict[str, Any] | None = None
    contacts: dict[str, Any] | None = None

    def sections(self) -> dict[str, dict[str, Any]]:
        return {s: v for s in _SECTIONS if (v := getattr(self, s)) is not None}


def _validate_section(section: str, value: Any, depth: int = 0) -> None:
    if depth > _MAX_OBJECT_DEPTH:
        raise ValidationError(f"'{section}' is nested too deeply.")
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise ValidationError(f"'{section}' has a value longer than {_MAX_STRING_LENGTH} characters.")
    elif isinstance(value, list):
        if len(value) > _MAX_ARRAY_ITEMS:
            raise ValidationError(f"'{section}' has more than {_MAX_ARRAY_ITEMS} items.")
        for item in value:
            _validate_section(section, item, depth + 1)
    elif isinstance(value, dict):
        for v in value.values():
            _validate_section(section, v, depth + 1)


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Patch values win; nested dicts merge recursively; anything else
    (including lists) is replaced outright, matching how the rest of this
    codebase treats JSON patches (see conversations.models JSON columns) —
    a caller that wants to remove one item from a list re-sends the whole
    list, it isn't diffed."""
    result = dict(target)
    for key, value in patch.items():
        if key in ("__proto__", "constructor"):
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


async def get_context(db: AsyncSession, org_id: uuid.UUID) -> BusinessContext:
    """Read-only. Called on every agent turn (see runtime/context_projector.py),
    so a brand-new org — the overwhelmingly common case, since nothing yet
    writes to this table — gets an unpersisted, empty, in-memory
    BusinessContext instead of an INSERT on its very first message. Nothing
    is written to the database until an owner actually sets something via
    update_context()."""
    result = await db.execute(select(BusinessContext).where(BusinessContext.org_id == org_id))
    context = result.scalar_one_or_none()
    return context if context is not None else BusinessContext(org_id=org_id)


async def _get_or_create(db: AsyncSession, org_id: uuid.UUID) -> BusinessContext:
    """Persisting variant for update_context()/reset_context(), where the
    caller is about to write and a real row is required."""
    result = await db.execute(select(BusinessContext).where(BusinessContext.org_id == org_id))
    context = result.scalar_one_or_none()
    if context is not None:
        return context

    context = BusinessContext(org_id=org_id)
    db.add(context)
    await db.commit()
    await db.refresh(context)
    return context


async def update_context(
    db: AsyncSession, org_id: uuid.UUID, patch: BusinessContextPatch
) -> BusinessContext:
    context = await _get_or_create(db, org_id)
    for section, value in patch.sections().items():
        _validate_section(section, value)
        setattr(context, section, _deep_merge(getattr(context, section), value))
    context.updated_at = _now()
    await db.commit()
    await db.refresh(context)
    return context


async def reset_context(db: AsyncSession, org_id: uuid.UUID) -> BusinessContext:
    context = await _get_or_create(db, org_id)
    for section in _SECTIONS:
        setattr(context, section, {})
    context.updated_at = _now()
    await db.commit()
    await db.refresh(context)
    return context
