"""Pack routes: any member can browse what's available/active; only an
owner/admin can activate or deactivate one; activation is isolated per
tenant and rejects a pack id that doesn't exist."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.identity.models import Membership, MembershipRole, Organization, User

PACK_ID = "pack_real_estate"


async def _member_headers(db: AsyncSession, org: Organization, role: MembershipRole) -> dict[str, str]:
    user = User(email=f"{role.value}-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", name="Someone")
    db.add(user)
    await db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role=role, accepted=True))
    await db.commit()
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}", "X-Organization-Id": str(org.id)}


async def test_list_packs_shows_none_active_for_new_org(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org
    response = await client.get(f"/api/v1/organizations/{org.id}/packs", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert any(p["id"] == PACK_ID for p in body)
    assert all(p["active"] is False for p in body)


async def test_owner_can_activate_and_deactivate(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org

    activate = await client.post(
        f"/api/v1/organizations/{org.id}/packs/{PACK_ID}/activate", headers=headers
    )
    assert activate.status_code == 200
    assert activate.json()["active"] is True

    listing = await client.get(f"/api/v1/organizations/{org.id}/packs", headers=headers)
    real_estate = next(p for p in listing.json() if p["id"] == PACK_ID)
    assert real_estate["active"] is True

    deactivate = await client.post(
        f"/api/v1/organizations/{org.id}/packs/{PACK_ID}/deactivate", headers=headers
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["active"] is False

    listing_after = await client.get(f"/api/v1/organizations/{org.id}/packs", headers=headers)
    assert next(p for p in listing_after.json() if p["id"] == PACK_ID)["active"] is False


async def test_member_cannot_activate(client: AsyncClient, db_session, user_and_org):
    _, org, _owner_headers = user_and_org
    member_headers = await _member_headers(db_session, org, MembershipRole.member)

    response = await client.post(
        f"/api/v1/organizations/{org.id}/packs/{PACK_ID}/activate", headers=member_headers
    )
    assert response.status_code == 403

    # A member can still browse the catalog.
    listing = await client.get(f"/api/v1/organizations/{org.id}/packs", headers=member_headers)
    assert listing.status_code == 200


async def test_activating_unknown_pack_is_404(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org
    response = await client.post(
        f"/api/v1/organizations/{org.id}/packs/pack_does_not_exist/activate", headers=headers
    )
    assert response.status_code == 404


async def test_activation_is_isolated_per_organization(client: AsyncClient, db_session, user_and_org):
    _, org_a, headers_a = user_and_org
    await client.post(f"/api/v1/organizations/{org_a.id}/packs/{PACK_ID}/activate", headers=headers_a)

    from src.identity.public_id import generate_public_id

    user_b = User(email="owner-b@example.com", hashed_password="x", name="Owner B")
    db_session.add(user_b)
    await db_session.flush()
    org_b = Organization(name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}", public_id=generate_public_id())
    db_session.add(org_b)
    await db_session.flush()
    db_session.add(
        Membership(user_id=user_b.id, organization_id=org_b.id, role=MembershipRole.owner, accepted=True)
    )
    await db_session.commit()
    headers_b = {
        "Authorization": f"Bearer {create_access_token(user_b.id)}",
        "X-Organization-Id": str(org_b.id),
    }

    listing_b = await client.get(f"/api/v1/organizations/{org_b.id}/packs", headers=headers_b)
    assert next(p for p in listing_b.json() if p["id"] == PACK_ID)["active"] is False
