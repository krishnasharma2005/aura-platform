"""Business context routes: an owner's own business facts (identity,
offerings, customers, brand, policies, operations, contacts), which every
agent's prompt is grounded in. See agents/business_context.py and
agents/runtime/context_projector.py for the storage and projection logic —
this module is purely the HTTP surface over it.

Any accepted member can read it (an agent's prompt is already built from it,
so hiding it from ordinary members would be security theater); only an
owner/admin can change it, matching the bar set for every other setting that
changes what agents say and do (see api/v1/organizations.py's public-chat
toggle, api/v1/workflows.py's enable/disable).
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import business_context as business_context_service
from src.agents.business_context import BusinessContext, BusinessContextPatch
from src.core.db import get_db
from src.core.exceptions import NotFoundError
from src.identity.deps import get_active_organization, require_org_role
from src.identity.models import MembershipRole, Organization

router = APIRouter(prefix="/organizations/{organization_id}/business-context", tags=["business-context"])

_editor = require_org_role(MembershipRole.owner, MembershipRole.admin)


class BusinessContextResponse(BaseModel):
    identity: dict[str, Any] = {}
    offerings: dict[str, Any] = {}
    customers: dict[str, Any] = {}
    brand: dict[str, Any] = {}
    policies: dict[str, Any] = {}
    operations: dict[str, Any] = {}
    contacts: dict[str, Any] = {}
    updated_at: datetime | None = None


class BusinessContextUpdateRequest(BaseModel):
    identity: dict[str, Any] | None = None
    offerings: dict[str, Any] | None = None
    customers: dict[str, Any] | None = None
    brand: dict[str, Any] | None = None
    policies: dict[str, Any] | None = None
    operations: dict[str, Any] | None = None
    contacts: dict[str, Any] | None = None


def _to_response(context: BusinessContext) -> BusinessContextResponse:
    return BusinessContextResponse(
        identity=context.identity or {},
        offerings=context.offerings or {},
        customers=context.customers or {},
        brand=context.brand or {},
        policies=context.policies or {},
        operations=context.operations or {},
        contacts=context.contacts or {},
        updated_at=context.updated_at,
    )


@router.get("", response_model=BusinessContextResponse)
async def get_business_context(
    organization_id: uuid.UUID,
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> BusinessContextResponse:
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    context = await business_context_service.get_context(db, organization.id)
    return _to_response(context)


@router.patch("", response_model=BusinessContextResponse)
async def update_business_context(
    organization_id: uuid.UUID,
    payload: BusinessContextUpdateRequest,
    organization: Organization = Depends(_editor),
    db: AsyncSession = Depends(get_db),
) -> BusinessContextResponse:
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    patch = BusinessContextPatch(**payload.model_dump())
    context = await business_context_service.update_context(db, organization.id, patch)
    return _to_response(context)


@router.post("/reset", response_model=BusinessContextResponse)
async def reset_business_context(
    organization_id: uuid.UUID,
    organization: Organization = Depends(_editor),
    db: AsyncSession = Depends(get_db),
) -> BusinessContextResponse:
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    context = await business_context_service.reset_context(db, organization.id)
    return _to_response(context)
