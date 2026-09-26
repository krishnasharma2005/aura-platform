"""Tests for the Google OAuth consent flow (src/tools/google_oauth.py,
wired into src/api/v1/integrations.py)."""

import uuid
from urllib.parse import parse_qs, urlsplit

import pytest

from src.core.config import get_settings
from src.tools import google_oauth
from src.tools.google_oauth import GoogleOAuthError
from src.tools.oauth_common import get_access_token, get_metadata, get_refresh_token, require_integration


@pytest.fixture
def google_oauth_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "test-client-id", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret", raising=False)
    return settings


def test_is_configured_requires_both_client_id_and_secret(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", None, raising=False)
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", None, raising=False)
    assert google_oauth.is_configured() is False

    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "id-only", raising=False)
    assert google_oauth.is_configured() is False

    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "secret-too", raising=False)
    assert google_oauth.is_configured() is True


def _query_params(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


async def test_build_authorize_url_carries_scopes_and_a_state_param(google_oauth_configured):
    org_id = uuid.uuid4()
    url = await google_oauth.build_authorize_url(org_id)
    params = _query_params(url)

    assert url.startswith(google_oauth.AUTHORIZE_URL)
    assert params["client_id"] == "test-client-id"
    assert params["access_type"] == "offline"
    assert params["prompt"] == "consent"
    assert set(params["scope"].split(" ")) == set(google_oauth.SCOPES)
    assert params["state"]


async def test_verify_state_round_trips_the_org_id(google_oauth_configured):
    org_id = uuid.uuid4()
    url = await google_oauth.build_authorize_url(org_id)
    state = _query_params(url)["state"]

    resolved_org_id = await google_oauth.verify_state(state)
    assert resolved_org_id == org_id


async def test_verify_state_rejects_a_replayed_state(google_oauth_configured):
    org_id = uuid.uuid4()
    url = await google_oauth.build_authorize_url(org_id)
    state = _query_params(url)["state"]

    await google_oauth.verify_state(state)  # first use succeeds and consumes the nonce
    with pytest.raises(GoogleOAuthError):
        await google_oauth.verify_state(state)  # replay is rejected


async def test_verify_state_rejects_a_garbage_token():
    with pytest.raises(GoogleOAuthError):
        await google_oauth.verify_state("not-a-real-jwt")


async def test_verify_state_rejects_a_token_of_the_wrong_type(google_oauth_configured):
    import jwt
    from datetime import UTC, datetime, timedelta

    settings = get_settings()
    forged = jwt.encode(
        {
            "org_id": str(uuid.uuid4()),
            "nonce": "whatever",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "type": "access",  # not "google_oauth_state"
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(GoogleOAuthError):
        await google_oauth.verify_state(forged)


async def test_connect_reports_coming_soon_when_google_oauth_is_not_configured(client, user_and_org, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", None, raising=False)
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", None, raising=False)
    _, _, headers = user_and_org

    response = await client.post("/api/v1/integrations/google/connect", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "coming_soon", "redirect_url": None}


async def test_connect_returns_a_real_redirect_url_when_configured(client, user_and_org, google_oauth_configured):
    _, _, headers = user_and_org

    response = await client.post("/api/v1/integrations/google/connect", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "redirect"
    assert body["redirect_url"].startswith(google_oauth.AUTHORIZE_URL)


async def test_callback_stores_the_integration_on_success(client, user_and_org, db_session, monkeypatch):
    user, org, headers = user_and_org

    async def _fake_exchange_code(code: str) -> dict:
        assert code == "auth-code-123"
        return {"access_token": "fake-access-token", "refresh_token": "fake-refresh-token"}

    async def _fake_fetch_email(access_token: str) -> str | None:
        assert access_token == "fake-access-token"
        return "owner@business.example"

    monkeypatch.setattr(google_oauth, "exchange_code", _fake_exchange_code)
    monkeypatch.setattr(google_oauth, "fetch_email", _fake_fetch_email)

    url = await google_oauth.build_authorize_url(org.id)
    state = _query_params(url)["state"]

    response = await client.get(
        "/api/v1/integrations/google/callback",
        params={"code": "auth-code-123", "state": state},
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert "google_connect=success" in response.headers["location"]

    integration = await require_integration(db_session, org.id, "google")
    assert get_access_token(integration) == "fake-access-token"
    assert get_refresh_token(integration) == "fake-refresh-token"
    assert get_metadata(integration)["account_label"] == "owner@business.example"


async def test_callback_redirects_with_an_error_flag_when_the_user_denies_consent(client):
    response = await client.get(
        "/api/v1/integrations/google/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "google_connect=denied" in response.headers["location"]


async def test_callback_redirects_with_an_error_flag_on_an_invalid_state(client):
    response = await client.get(
        "/api/v1/integrations/google/callback",
        params={"code": "whatever", "state": "not-a-real-state"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "google_connect=error" in response.headers["location"]


async def test_callback_redirects_with_an_error_flag_when_token_exchange_fails(
    client, user_and_org, monkeypatch
):
    _, org, _ = user_and_org

    async def _failing_exchange(code: str) -> dict:
        raise GoogleOAuthError("Google didn't accept that connection request.")

    monkeypatch.setattr(google_oauth, "exchange_code", _failing_exchange)

    url = await google_oauth.build_authorize_url(org.id)
    state = _query_params(url)["state"]

    response = await client.get(
        "/api/v1/integrations/google/callback",
        params={"code": "auth-code-123", "state": state},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "google_connect=error" in response.headers["location"]
