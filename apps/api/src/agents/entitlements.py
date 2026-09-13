"""Per-organization Business Pack entitlements — which purchasable vertical
packs (real estate, legal, dental, ...) an org has activated on top of the
six base agents.

Ported from dist/mesnium-business/entitlements-store.js in the openclaw/claw
fork this was mapped from, replacing its per-workspace JSON file on disk with
a proper org-scoped table, consistent with how every other piece of tenant
state in this codebase works (see agents/approvals.py for the same pattern:
model + service functions colocated in one module).

What this module deliberately does NOT do yet:
  - Enforce billing. Activating a pack here does not charge anyone and
    deactivating it does not refund anyone — this is entitlement bookkeeping
    only. The checkout flow that calls activate_pack() is a separate,
    not-yet-built piece.
  - Apply a pack's agent_overrides to anything. See
    agents/runtime/pack_loader.py for the pack schema and its own scope note
    — merging an active pack's overrides onto the base AgentConfig at
    runtime ("the context merge engine") is a separate, larger piece of work
    that reads list_active_pack_ids() from here as an input.

Absence of a row for (org_id, pack_id) means "never activated" — there is no
default-on pack; every organization starts with only the six base agents.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.agents.runtime.pack_loader import get_pack
from src.core.db import Base
from src.core.exceptions import NotFoundError


class OrgPackEntitlement(Base):
    """One organization's activation state for one pack."""

    __tablename__ = "org_pack_entitlements"
    __table_args__ = (
        UniqueConstraint("org_id", "pack_id", name="uq_org_pack_entitlements_org_pack"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # Not a foreign key: packs are defined in YAML (agents/runtime/pack_loader.py),
    # not a database table, the same way agent slugs in requires_approval
    # aren't foreign keys either.
    pack_id: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    activated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def list_entitlements_for_org(db: AsyncSession, org_id: uuid.UUID) -> list[OrgPackEntitlement]:
    """All entitlement rows for an org, active or not — the settings/checkout
    UI needs to show deactivated packs too (so an owner can re-enable one)."""
    stmt = select(OrgPackEntitlement).where(OrgPackEntitlement.org_id == org_id)
    return list((await db.execute(stmt)).scalars().all())


async def list_active_pack_ids(db: AsyncSession, org_id: uuid.UUID) -> list[str]:
    stmt = select(OrgPackEntitlement.pack_id).where(
        OrgPackEntitlement.org_id == org_id, OrgPackEntitlement.enabled.is_(True)
    )
    return list((await db.execute(stmt)).scalars().all())


async def is_pack_active(db: AsyncSession, org_id: uuid.UUID, pack_id: str) -> bool:
    return pack_id in await list_active_pack_ids(db, org_id)


async def activate_pack(db: AsyncSession, org_id: uuid.UUID, pack_id: str) -> OrgPackEntitlement:
    """Activates pack_id for org_id. Idempotent: re-activating an already
    -active pack just re-enables it (and clears deactivated_at) instead of
    erroring or creating a duplicate row, since a checkout webhook calling
    this may retry."""
    get_pack(pack_id)  # raises PackNotFoundError for an unknown pack_id —
    # never let a typo silently create an entitlement to nothing.

    existing = await db.execute(
        select(OrgPackEntitlement).where(
            OrgPackEntitlement.org_id == org_id, OrgPackEntitlement.pack_id == pack_id
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        row.enabled = True
        row.deactivated_at = None
    else:
        row = OrgPackEntitlement(org_id=org_id, pack_id=pack_id, enabled=True)
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def deactivate_pack(db: AsyncSession, org_id: uuid.UUID, pack_id: str) -> OrgPackEntitlement:
    result = await db.execute(
        select(OrgPackEntitlement).where(
            OrgPackEntitlement.org_id == org_id, OrgPackEntitlement.pack_id == pack_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("That pack isn't active for this organization.")
    row.enabled = False
    row.deactivated_at = _now()
    await db.commit()
    await db.refresh(row)
    return row
