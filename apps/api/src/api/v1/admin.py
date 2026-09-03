"""Admin routes: list users/roles for an org."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.identity.deps import require_org_role
from src.identity.models import Membership, MembershipRole, Organization, User
from src.identity.schemas import MembershipResponse

router = APIRouter(prefix="/admin", tags=["admin"])


class MemberWithUser(MembershipResponse):
    email: str | None = None
    name: str | None = None


@router.get("/users", response_model=list[MemberWithUser])
async def list_org_users(
    organization: Organization = Depends(require_org_role(MembershipRole.owner, MembershipRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> list[MemberWithUser]:
    result = await db.execute(
        select(Membership, User)
        .outerjoin(User, Membership.user_id == User.id)
        .where(Membership.organization_id == organization.id)
    )
    members = []
    for membership, user in result.all():
        members.append(
            MemberWithUser(
                id=membership.id,
                user_id=membership.user_id,
                organization_id=membership.organization_id,
                role=membership.role,
                invited_email=membership.invited_email,
                accepted=membership.accepted,
                created_at=membership.created_at,
                email=user.email if user else None,
                name=user.name if user else None,
            )
        )
    return members
