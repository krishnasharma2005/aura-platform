"""Organization routes: create org, invite members, list members."""

import re
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.exceptions import ConflictError, NotFoundError, PermissionError
from src.identity.deps import get_active_organization, get_current_user, require_org_role
from src.identity.models import Membership, MembershipRole, Organization, User
from src.identity.public_id import generate_public_id
from src.identity.schemas import (
    InviteRequest,
    MembershipResponse,
    OrganizationCreateRequest,
    OrganizationResponse,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


async def _unique_slug(db: AsyncSession, name: str) -> str:
    """The client no longer picks a slug (it's an internal URL/identity detail,
    not something an SMB owner should have to think about at signup) — derive
    one from the org name and disambiguate on collision."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    slug = base
    suffix = 1
    while (await db.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none():
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    slug = await _unique_slug(db, payload.name)
    org = Organization(
        name=payload.name,
        slug=slug,
        business_type=payload.business_type,
        primary_goal=payload.primary_goal,
        public_id=generate_public_id(),
    )
    db.add(org)
    await db.flush()

    owner_membership = Membership(
        user_id=current_user.id,
        organization_id=org.id,
        role=MembershipRole.owner,
        accepted=True,
    )
    db.add(owner_membership)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("", response_model=list[OrganizationResponse])
async def list_my_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Organization]:
    """Every organization the caller actually belongs to.

    This is how a returning user's client discovers which tenant to put in
    X-Organization-Id. Without it only a brand-new user who just created an org
    during onboarding had an active tenant, and everyone else's org-scoped
    requests 404'd. Scoped by accepted membership, so it can never reveal an
    organization the caller isn't in.
    """
    stmt = (
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == current_user.id, Membership.accepted.is_(True))
        .order_by(Organization.created_at)
    )
    organizations = list((await db.execute(stmt)).scalars().all())

    # Orgs created before public chat existed have no public_id; mint one on
    # read rather than requiring a data backfill (same rule as the detail route).
    minted = False
    for organization in organizations:
        if organization.public_id is None:
            organization.public_id = generate_public_id()
            minted = True
    if minted:
        await db.commit()

    return organizations


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: uuid.UUID,
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Reads the active org, including the public web-chat id the owner needs
    in order to embed the widget. Orgs created before public chat existed have
    no id yet, so one is minted on first read."""
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    if organization.public_id is None:
        organization.public_id = generate_public_id()
        await db.commit()
        await db.refresh(organization)
    return organization


@router.post("/{organization_id}/public-chat/rotate", response_model=OrganizationResponse)
async def rotate_public_chat_id(
    organization_id: uuid.UUID,
    organization: Organization = Depends(require_org_role(MembershipRole.owner, MembershipRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Issues a new public web-chat id, immediately invalidating any widget
    embedded with the old one. This is the "someone is abusing our chat link"
    lever — owner/admin only."""
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    organization.public_id = generate_public_id()
    await db.commit()
    await db.refresh(organization)
    return organization


@router.post("/{organization_id}/public-chat/enable", response_model=OrganizationResponse)
async def enable_public_chat(
    organization_id: uuid.UUID,
    organization: Organization = Depends(require_org_role(MembershipRole.owner, MembershipRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Turns website chat on. Owner/admin only — this is what a website
    visitor everywhere on the internet can reach once it's on."""
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    if organization.public_id is None:
        organization.public_id = generate_public_id()
    organization.public_chat_enabled = True
    await db.commit()
    await db.refresh(organization)
    return organization


@router.post("/{organization_id}/public-chat/disable", response_model=OrganizationResponse)
async def disable_public_chat(
    organization_id: uuid.UUID,
    organization: Organization = Depends(require_org_role(MembershipRole.owner, MembershipRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Turns website chat off. The embed script keeps working on the owner's
    site (nothing to re-paste) but renders nothing — see
    api/v1/public.py::_resolve_org, which treats a disabled org exactly like
    an org that doesn't exist."""
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")
    organization.public_chat_enabled = False
    await db.commit()
    await db.refresh(organization)
    return organization


@router.post(
    "/{organization_id}/invite",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    organization_id: uuid.UUID,
    payload: InviteRequest,
    organization: Organization = Depends(require_org_role(MembershipRole.owner, MembershipRole.admin)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Membership:
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")

    # Only an owner can grant the owner role — an admin inviting someone as
    # "owner" would otherwise be a privilege escalation.
    caller_membership = await db.execute(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.organization_id == organization.id,
            Membership.accepted.is_(True),
        )
    )
    caller_role = caller_membership.scalar_one().role
    if payload.role == MembershipRole.owner and caller_role != MembershipRole.owner:
        raise PermissionError("Only an owner can grant the owner role.")

    result = await db.execute(select(User).where(User.email == payload.email))
    invited_user = result.scalar_one_or_none()

    if invited_user is not None:
        existing = await db.execute(
            select(Membership).where(
                Membership.user_id == invited_user.id,
                Membership.organization_id == organization.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("That person is already a member of this organization.")

    membership = Membership(
        user_id=invited_user.id if invited_user else None,
        organization_id=organization.id,
        role=payload.role,
        invited_email=payload.email,
        accepted=invited_user is not None,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership


@router.get("/{organization_id}/members", response_model=list[MembershipResponse])
async def list_members(
    organization_id: uuid.UUID,
    organization: Organization = Depends(require_org_role(MembershipRole.owner, MembershipRole.admin, MembershipRole.member)),
    db: AsyncSession = Depends(get_db),
) -> list[Membership]:
    if organization.id != organization_id:
        raise NotFoundError("That organization doesn't exist.")

    result = await db.execute(select(Membership).where(Membership.organization_id == organization.id))
    return list(result.scalars().all())
