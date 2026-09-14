"""Pack routes: which vertical Business Packs exist, and which ones this
organization has activated.

See agents/runtime/pack_loader.py (pack definitions, loaded from YAML — not
a database table) and agents/entitlements.py (per-org activation state, the
actual table) for what a pack is and what activating one does and does not
do yet — most importantly, this does not charge anyone; see
entitlements.py's module docstring.

Listing is open to any accepted member (browsing what's available/active
isn't sensitive); activating or deactivating is owner/admin only, the same
bar as every other setting with a real effect on what agents do.
"""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import entitlements as entitlements_service
from src.agents.runtime.pack_loader import Pack, PackNotFoundError, get_pack, list_packs
from src.core.db import get_db
from src.core.exceptions import NotFoundError
from src.identity.deps import get_active_organization, require_org_role
from src.identity.models import MembershipRole, Organization

router = APIRouter(prefix="/organizations/{organization_id}/packs", tags=["packs"])

_activator = require_org_role(MembershipRole.owner, MembershipRole.admin)


class PackResponse(BaseModel):
    id: str
    name: str
    version: str
    category: str
    description: str
    capability_requirements: list[str] = []
    active: bool = False


def _to_response(pack: Pack, active_pack_ids: set[str]) -> PackResponse:
    return PackResponse(
        id=pack.id,
        name=pack.name,
        version=pack.version,
        category=pack.category,
        description=pack.description,
        capability_requirements=pack.capability_requirements,
        active=pack.id in active_pack_ids,
    )


def _get_pack_or_404(pack_id: str) -> Pack:
    try:
        return get_pack(pack_id)
    except PackNotFoundError as exc:
        raise NotFoundError("That pack doesn't exist.") from exc


@router.get("", response_model=list[PackResponse])
async def list_org_packs(
    organization_id: uuid.UUID,
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> list[PackResponse]:
    """Every pack that exists, each annotated with whether this org has it
    active — what a settings/checkout page needs in one call."""
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    active_ids = set(await entitlements_service.list_active_pack_ids(db, organization.id))
    return [_to_response(pack, active_ids) for pack in list_packs()]


@router.post("/{pack_id}/activate", response_model=PackResponse)
async def activate_pack(
    organization_id: uuid.UUID,
    pack_id: str,
    organization: Organization = Depends(_activator),
    db: AsyncSession = Depends(get_db),
) -> PackResponse:
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    pack = _get_pack_or_404(pack_id)
    await entitlements_service.activate_pack(db, organization.id, pack_id)
    return _to_response(pack, active_pack_ids={pack_id})


@router.post("/{pack_id}/deactivate", response_model=PackResponse)
async def deactivate_pack(
    organization_id: uuid.UUID,
    pack_id: str,
    organization: Organization = Depends(_activator),
    db: AsyncSession = Depends(get_db),
) -> PackResponse:
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    pack = _get_pack_or_404(pack_id)
    await entitlements_service.deactivate_pack(db, organization.id, pack_id)
    return _to_response(pack, active_pack_ids=set())
