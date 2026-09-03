"""FastAPI dependencies for authentication, RBAC, and tenant (organization)
resolution. The tenant dependency is load-bearing: every route that touches
org-scoped data must depend on `get_active_organization` (or `require_org_role`)
so no query can ever cross organization boundaries."""

import uuid

import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.exceptions import AuthenticationError, NotFoundError, PermissionError
from src.core.security import decode_token
from src.identity.models import Membership, MembershipRole, Organization, User


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Please sign in to continue.")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Your session has expired. Please sign in again.") from exc
    if payload.get("type") != "access":
        raise AuthenticationError("Please sign in again.")
    # `sub` is attacker-controllable in shape: a missing or non-UUID claim must
    # read as "sign in again", never as an unhandled 500.
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("Please sign in again.") from exc
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError("Please sign in again.")
    return user


async def get_active_organization(
    x_organization_id: str | None = Header(default=None, alias="X-Organization-Id"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Resolves the active org from the `X-Organization-Id` header and confirms
    the current user has an accepted membership in it. This is the single choke
    point that enforces tenant isolation for header-scoped routes."""
    if not x_organization_id:
        raise NotFoundError("No organization was specified.")
    try:
        org_id = uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise NotFoundError("That organization doesn't exist.") from exc

    membership = await _get_accepted_membership(db, current_user.id, org_id)
    if membership is None:
        raise PermissionError("You don't have access to this organization.")

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise NotFoundError("That organization doesn't exist.")
    return org


async def _get_accepted_membership(
    db: AsyncSession, user_id: uuid.UUID, organization_id: uuid.UUID
) -> Membership | None:
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
            Membership.accepted.is_(True),
        )
    )
    return result.scalar_one_or_none()


def require_org_role(*roles: MembershipRole):
    """Returns a dependency that resolves the active org AND asserts the current
    user's membership role is one of `roles`. Use for admin-only actions."""

    async def _dependency(
        organization: Organization = Depends(get_active_organization),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Organization:
        membership = await _get_accepted_membership(db, current_user.id, organization.id)
        if membership is None or membership.role not in roles:
            raise PermissionError("You don't have permission to do that.")
        return organization

    return _dependency
