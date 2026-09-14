"""Business context routes: an owner's business facts are readable by any
member, writable only by an owner/admin, isolated per tenant, and validated
against oversized input."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.identity.models import Membership, MembershipRole, Organization, User
from src.identity.public_id import generate_public_id


async def _member_headers(db: AsyncSession, org: Organization, role: MembershipRole) -> dict[str, str]:
    user = User(email=f"{role.value}-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", name="Someone")
    db.add(user)
    await db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role=role, accepted=True))
    await db.commit()
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}", "X-Organization-Id": str(org.id)}


async def test_new_org_has_empty_context(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org
    response = await client.get(f"/api/v1/organizations/{org.id}/business-context", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["identity"] == {}
    assert body["updated_at"] is None


async def test_owner_can_set_context(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org
    response = await client.patch(
        f"/api/v1/organizations/{org.id}/business-context",
        headers=headers,
        json={"identity": {"business_name": "Riverside Dental", "industry": "Dental Clinic"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["identity"]["business_name"] == "Riverside Dental"
    assert body["updated_at"] is not None

    # Reading it back returns the same data.
    read_back = await client.get(f"/api/v1/organizations/{org.id}/business-context", headers=headers)
    assert read_back.json()["identity"]["business_name"] == "Riverside Dental"


async def test_partial_patch_preserves_other_sections(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org
    await client.patch(
        f"/api/v1/organizations/{org.id}/business-context",
        headers=headers,
        json={
            "identity": {"business_name": "Riverside Dental"},
            "brand": {"tone": "Warm and reassuring"},
        },
    )
    second = await client.patch(
        f"/api/v1/organizations/{org.id}/business-context",
        headers=headers,
        json={"identity": {"industry": "Dental Clinic"}},
    )
    body = second.json()
    assert body["identity"]["business_name"] == "Riverside Dental"
    assert body["identity"]["industry"] == "Dental Clinic"
    assert body["brand"]["tone"] == "Warm and reassuring"


async def test_member_cannot_edit_context(client: AsyncClient, db_session, user_and_org):
    _, org, _owner_headers = user_and_org
    member_headers = await _member_headers(db_session, org, MembershipRole.member)

    response = await client.patch(
        f"/api/v1/organizations/{org.id}/business-context",
        headers=member_headers,
        json={"identity": {"business_name": "Should Not Work"}},
    )
    assert response.status_code == 403

    # But a member CAN read it.
    read = await client.get(f"/api/v1/organizations/{org.id}/business-context", headers=member_headers)
    assert read.status_code == 200


async def test_oversized_field_is_rejected(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org
    response = await client.patch(
        f"/api/v1/organizations/{org.id}/business-context",
        headers=headers,
        json={"identity": {"description": "x" * 2000}},
    )
    assert response.status_code == 422


async def test_reset_clears_context(client: AsyncClient, user_and_org):
    _, org, headers = user_and_org
    await client.patch(
        f"/api/v1/organizations/{org.id}/business-context",
        headers=headers,
        json={"identity": {"business_name": "Riverside Dental"}},
    )
    response = await client.post(f"/api/v1/organizations/{org.id}/business-context/reset", headers=headers)
    assert response.status_code == 200
    assert response.json()["identity"] == {}


async def test_context_is_isolated_per_organization(client: AsyncClient, db_session, user_and_org):
    _, org_a, headers_a = user_and_org
    await client.patch(
        f"/api/v1/organizations/{org_a.id}/business-context",
        headers=headers_a,
        json={"identity": {"business_name": "Org A Business"}},
    )

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

    response = await client.get(f"/api/v1/organizations/{org_b.id}/business-context", headers=headers_b)
    assert response.json()["identity"] == {}

    # And org B has no access to org A's context at all. A path org id that
    # doesn't match the caller's active (header) org reads as not-found, the
    # same as every other org-scoped route (see organizations.py) — it never
    # confirms org A even exists.
    cross_tenant = await client.get(f"/api/v1/organizations/{org_a.id}/business-context", headers=headers_b)
    assert cross_tenant.status_code == 404
