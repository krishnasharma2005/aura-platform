"""Connecting WhatsApp, Slack, HubSpot and Shopify by pasting a key — the check
before saving, the safety of what we call, who may do it, and disconnecting.

No real accounts are involved: the one function that touches the network
(`credentials._request`) is replaced with a recorder, so a test can also assert
that an unsafe address caused *no request at all*."""

import httpx
import pytest

from src.core.security import create_access_token
from src.identity.models import Membership, MembershipRole, User
from src.tools import credentials, google_oauth
from src.tools.oauth_common import get_access_token, get_metadata, get_refresh_token, require_integration
from src.core.exceptions import ProviderNotConfiguredError


class _Reply:
    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body


@pytest.fixture
def network(monkeypatch):
    """Record every outbound call and answer from a per-test script."""

    class _Net:
        calls: list[tuple[str, str, dict]] = []
        reply: _Reply | Exception = _Reply()

    _Net.calls = []
    _Net.reply = _Reply()

    async def _fake_request(method, url, **kwargs):
        _Net.calls.append((method, url, kwargs))
        if isinstance(_Net.reply, Exception):
            raise _Net.reply
        return _Net.reply

    monkeypatch.setattr(credentials, "_request", _fake_request)
    return _Net


async def _connect(client, headers, provider, token, metadata=None):
    return await client.post(
        "/api/v1/integrations",
        json={"provider": provider, "access_token": token, "metadata": metadata},
        headers=headers,
    )


# ------------------------------------------------------------------- shopify


async def test_shopify_connects_and_remembers_the_store_name(client, user_and_org, db_session, network):
    _, org, headers = user_and_org
    network.reply = _Reply(200, {"shop": {"name": "Smile Supplies"}})

    response = await _connect(client, headers, "shopify", "shpat_abc123", {"shop_domain": "https://Smile-Supplies.myshopify.com/admin"})

    assert response.status_code == 200
    assert response.json()["connected"] is True
    method, url, kwargs = network.calls[0]
    assert url == "https://smile-supplies.myshopify.com/admin/api/2024-10/shop.json"
    assert kwargs["headers"]["X-Shopify-Access-Token"] == "shpat_abc123"

    integration = await require_integration(db_session, org.id, "shopify")
    assert get_access_token(integration) == "shpat_abc123"
    metadata = get_metadata(integration)
    assert metadata["shop_domain"] == "smile-supplies.myshopify.com"  # normalised
    assert metadata["account_label"] == "Smile Supplies"
    assert metadata["connected_at"]


@pytest.mark.parametrize(
    "address",
    [
        "evil.com",
        "shop.myshopify.com.evil.com",
        "169.254.169.254",
        "localhost:8000",
        "http://127.0.0.1/admin",
        "my shop.myshopify.com",
        "",
    ],
)
async def test_an_unsafe_shopify_address_is_refused_before_any_request_is_made(
    client, user_and_org, network, address
):
    _, _, headers = user_and_org

    response = await _connect(client, headers, "shopify", "shpat_x", {"shop_domain": address})

    assert response.status_code == 422
    assert "myshopify.com" in response.json()["error"]
    assert network.calls == []  # nothing was ever requested from that address


async def test_a_wrong_shopify_token_is_rejected_and_nothing_is_saved(client, user_and_org, db_session, network):
    _, org, headers = user_and_org
    network.reply = _Reply(401, {"errors": "[API] Invalid API key or access token"})

    response = await _connect(client, headers, "shopify", "shpat_wrong", {"shop_domain": "shop.myshopify.com"})

    assert response.status_code == 422
    assert "didn't accept that access token" in response.json()["error"]
    with pytest.raises(ProviderNotConfiguredError):
        await require_integration(db_session, org.id, "shopify")


# ------------------------------------------------------------------- whatsapp


async def test_whatsapp_connects_and_keeps_only_the_phone_number_id(client, user_and_org, db_session, network):
    _, org, headers = user_and_org
    network.reply = _Reply(200, {"verified_name": "Smile Dental", "display_phone_number": "+44 7700 900123"})

    response = await _connect(
        client, headers, "whatsapp", "EAAGtoken", {"phone_number_id": "109876543210", "sneaky": "<script>"}
    )

    assert response.status_code == 200
    assert network.calls[0][1] == "https://graph.facebook.com/v21.0/109876543210"
    metadata = get_metadata(await require_integration(db_session, org.id, "whatsapp"))
    assert metadata["phone_number_id"] == "109876543210"
    assert metadata["account_label"] == "Smile Dental"
    assert "sneaky" not in metadata  # only whitelisted details are stored


@pytest.mark.parametrize("phone_number_id", ["+447700900123", "123/../456", "abc", "12"])
async def test_a_whatsapp_phone_number_id_must_be_just_digits(client, user_and_org, network, phone_number_id):
    _, _, headers = user_and_org

    response = await _connect(client, headers, "whatsapp", "EAAGtoken", {"phone_number_id": phone_number_id})

    assert response.status_code == 422
    assert network.calls == []


async def test_a_whatsapp_rejection_explains_both_values_must_match(client, user_and_org, network):
    _, _, headers = user_and_org
    network.reply = _Reply(400, {"error": {"message": "Invalid OAuth access token"}})

    response = await _connect(client, headers, "whatsapp", "EAAGbad", {"phone_number_id": "109876543210"})

    assert response.status_code == 422
    assert "same WhatsApp app" in response.json()["error"]


# ------------------------------------------------------------- slack & hubspot


async def test_slack_connects_with_a_good_token_and_rejects_a_bad_one(client, user_and_org, network):
    _, _, headers = user_and_org

    network.reply = _Reply(200, {"ok": False, "error": "invalid_auth"})
    bad = await _connect(client, headers, "slack", "xoxb-bad")
    assert bad.status_code == 422
    assert "xoxb-" in bad.json()["error"]

    network.reply = _Reply(200, {"ok": True, "team": "Smile Dental"})
    good = await _connect(client, headers, "slack", "xoxb-good")
    assert good.status_code == 200
    assert good.json()["metadata"]["team"] == "Smile Dental"


async def test_hubspot_distinguishes_a_wrong_token_from_missing_permissions(client, user_and_org, network):
    _, _, headers = user_and_org

    network.reply = _Reply(401)
    wrong = await _connect(client, headers, "hubspot", "pat-wrong")
    assert wrong.status_code == 422
    assert "didn't accept that token" in wrong.json()["error"]

    network.reply = _Reply(403)
    scope = await _connect(client, headers, "hubspot", "pat-noscope")
    assert scope.status_code == 422
    assert "contacts read and write" in scope.json()["error"]

    network.reply = _Reply(200, {"results": []})
    good = await _connect(client, headers, "hubspot", "pat-good")
    assert good.status_code == 200


async def test_an_unreachable_app_gives_a_try_again_message_and_saves_nothing(client, user_and_org, db_session, network):
    _, org, headers = user_and_org
    network.reply = httpx.ConnectTimeout("timed out")

    response = await _connect(client, headers, "slack", "xoxb-anything")

    assert response.status_code == 422
    assert "couldn't reach Slack" in response.json()["error"]
    with pytest.raises(ProviderNotConfiguredError):
        await require_integration(db_session, org.id, "slack")


async def test_an_empty_or_oversized_key_is_refused_without_a_request(client, user_and_org, network):
    _, _, headers = user_and_org

    assert (await _connect(client, headers, "slack", "   ")).status_code == 422
    assert (await _connect(client, headers, "slack", "x" * 5000)).status_code == 422
    assert network.calls == []


# ----------------------------------------------------------- who, what, listing


async def test_an_unknown_provider_cannot_be_connected(client, user_and_org, network):
    _, _, headers = user_and_org

    response = await _connect(client, headers, "myspace", "token")

    assert response.status_code == 422


async def test_only_owners_and_admins_can_connect_or_disconnect(client, user_and_org, db_session, network):
    _, org, headers = user_and_org
    member = User(email="staff@example.com", hashed_password="x", name="Staff")
    db_session.add(member)
    await db_session.flush()
    db_session.add(Membership(user_id=member.id, organization_id=org.id, role=MembershipRole.member, accepted=True))
    await db_session.commit()
    member_headers = {"Authorization": f"Bearer {create_access_token(member.id)}", "X-Organization-Id": str(org.id)}
    network.reply = _Reply(200, {"ok": True, "team": "T"})

    assert (await _connect(client, member_headers, "slack", "xoxb-1")).status_code == 403
    assert (await client.delete("/api/v1/integrations/slack", headers=member_headers)).status_code == 403
    assert network.calls == []
    # ...but they can still see what's connected.
    assert (await client.get("/api/v1/integrations", headers=member_headers)).status_code == 200


async def test_the_list_shows_the_account_but_never_the_token(client, user_and_org, network):
    _, _, headers = user_and_org
    network.reply = _Reply(200, {"ok": True, "team": "Smile Dental"})
    await _connect(client, headers, "slack", "xoxb-super-secret-token")

    listed = await client.get("/api/v1/integrations", headers=headers)

    slack = next(row for row in listed.json() if row["provider"] == "slack")
    assert slack["connected"] is True
    assert slack["metadata"]["account_label"] == "Smile Dental"
    assert "xoxb-super-secret-token" not in listed.text


async def test_the_connect_button_asks_for_a_key_for_these_apps(client, user_and_org):
    _, _, headers = user_and_org

    for provider in ("whatsapp", "slack", "hubspot", "shopify"):
        response = await client.post(f"/api/v1/integrations/{provider}/connect", headers=headers)
        assert response.json() == {"status": "needs_credentials", "redirect_url": None}


# ------------------------------------------------------------------ disconnect


async def test_disconnecting_forgets_the_credentials_and_is_safe_to_repeat(client, user_and_org, db_session, network):
    _, org, headers = user_and_org
    network.reply = _Reply(200, {"ok": True, "team": "T"})
    await _connect(client, headers, "slack", "xoxb-1")

    first = await client.delete("/api/v1/integrations/slack", headers=headers)
    second = await client.delete("/api/v1/integrations/slack", headers=headers)

    assert first.status_code == 204 and second.status_code == 204
    with pytest.raises(ProviderNotConfiguredError):
        await require_integration(db_session, org.id, "slack")
    listed = (await client.get("/api/v1/integrations", headers=headers)).json()
    assert next(row for row in listed if row["provider"] == "slack")["connected"] is False


async def test_disconnecting_google_also_asks_google_to_revoke(client, user_and_org, db_session, monkeypatch):
    from src.tools.oauth_common import store_integration

    _, org, headers = user_and_org
    await store_integration(db_session, org.id, "google", "access-1", refresh_token="refresh-1", metadata={})
    revoked: list[str | None] = []

    async def _fake_revoke(token):
        revoked.append(token)

    monkeypatch.setattr(google_oauth, "revoke", _fake_revoke)

    response = await client.delete("/api/v1/integrations/google", headers=headers)

    assert response.status_code == 204
    assert revoked == ["refresh-1"]  # the long-lived token is the one that matters
    with pytest.raises(ProviderNotConfiguredError):
        await require_integration(db_session, org.id, "google")


async def test_one_orgs_disconnect_never_touches_anothers(client, user_and_org, db_session, network):
    from src.identity.models import Organization
    from src.identity.public_id import generate_public_id
    from src.tools.oauth_common import store_integration

    _, org, headers = user_and_org
    other = Organization(name="Other", slug="other-org-x", public_id=generate_public_id())
    db_session.add(other)
    await db_session.commit()
    await store_integration(db_session, other.id, "slack", "xoxb-other", metadata={})

    await client.delete("/api/v1/integrations/slack", headers=headers)

    still_there = await require_integration(db_session, other.id, "slack")
    assert get_access_token(still_there) == "xoxb-other"
