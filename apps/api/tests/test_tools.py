"""Tool adapter behaviour that isn't covered by the runtime tests: credential
encryption at rest, calendar time handling, and argument validation."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import crypto
from src.tools.calendar import CalendarTool, get_org_timezone
from src.tools.models import Integration
from src.tools.oauth_common import get_access_token, get_refresh_token, store_integration
from src.tools.registry import TOOL_REGISTRY


@pytest.fixture
def encryption_key(monkeypatch):
    from cryptography.fernet import Fernet

    from src.core.config import get_settings

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(get_settings(), "ENCRYPTION_KEY", key, raising=False)
    crypto._get_fernet.cache_clear()
    yield key
    crypto._get_fernet.cache_clear()


async def test_tokens_are_encrypted_at_rest_and_read_back(db_session: AsyncSession, user_and_org, encryption_key):
    """The ciphertext in the table must not contain the token, but the tool
    layer must still get the real value back."""
    _, org, _ = user_and_org

    await store_integration(
        db_session, org_id=org.id, provider="slack", access_token="xoxb-super-secret", refresh_token="refresh-secret"
    )

    row = (
        await db_session.execute(select(Integration).where(Integration.org_id == org.id))
    ).scalar_one()
    assert "xoxb-super-secret" not in row.access_token
    assert "refresh-secret" not in (row.refresh_token or "")
    assert row.access_token.startswith("enc:v1:")

    assert get_access_token(row) == "xoxb-super-secret"
    assert get_refresh_token(row) == "refresh-secret"


async def test_legacy_plaintext_tokens_are_still_readable(db_session: AsyncSession, user_and_org, encryption_key):
    """Migration path: rows written before encryption was switched on have no
    `enc:v1:` prefix and must keep working rather than breaking the connection."""
    _, org, _ = user_and_org

    db_session.add(Integration(org_id=org.id, provider="hubspot", access_token="legacy-plaintext-token"))
    await db_session.commit()

    row = (
        await db_session.execute(
            select(Integration).where(Integration.org_id == org.id, Integration.provider == "hubspot")
        )
    ).scalar_one()
    assert get_access_token(row) == "legacy-plaintext-token"


async def test_calendar_list_is_anchored_at_now_and_carries_the_timezone(user_and_org, monkeypatch):
    """Regression: list_events had no timeMin, so it returned the ten *oldest*
    events in the calendar's history instead of what's coming up."""
    captured: dict = {}

    class _FakeEvents:
        def list(self, **kwargs):
            captured.update(kwargs)
            return self

        def execute(self):
            return {"items": []}

    class _FakeService:
        def events(self):
            return _FakeEvents()

    tool = CalendarTool()
    monkeypatch.setattr(CalendarTool, "_service", staticmethod(lambda credentials: _FakeService()))

    tool._list_events(credentials=None, timezone="Europe/London")

    assert "timeMin" in captured
    assert captured["timeZone"] == "Europe/London"
    assert captured["orderBy"] == "startTime"
    assert captured["singleEvents"] is True


async def test_calendar_create_sends_an_explicit_timezone(user_and_org, db_session, monkeypatch):
    """"Tuesday at 3pm" must be 3pm where the business is, not 3pm UTC."""
    _, org, _ = user_and_org
    org.timezone = "Europe/London"
    await db_session.commit()

    from src.tools import calendar as calendar_module

    await store_integration(db_session, org_id=org.id, provider="google", access_token="tok")

    captured: dict = {}

    def _fake_free_busy(self, credentials, start_time, end_time, timezone):
        return []

    def _fake_create(self, credentials, body):
        captured.update(body)
        return {"id": "evt_1"}

    monkeypatch.setattr(calendar_module.CalendarTool, "_free_busy", _fake_free_busy)
    monkeypatch.setattr(calendar_module.CalendarTool, "_create_event", _fake_create)
    monkeypatch.setattr(calendar_module, "Credentials", lambda **kwargs: None)

    result = await TOOL_REGISTRY["calendar"].execute(
        db_session,
        org.id,
        action="create_event",
        start_time="2026-08-18T15:00:00",
        end_time="2026-08-18T16:00:00",
    )

    assert result.success is True
    assert captured["start"]["timeZone"] == "Europe/London"
    assert captured["end"]["timeZone"] == "Europe/London"


async def test_calendar_refuses_to_double_book(user_and_org, db_session, monkeypatch):
    _, org, _ = user_and_org
    from src.tools import calendar as calendar_module

    await store_integration(db_session, org_id=org.id, provider="google", access_token="tok")

    monkeypatch.setattr(
        calendar_module.CalendarTool,
        "_free_busy",
        lambda self, credentials, start_time, end_time, timezone: [{"start": start_time, "end": end_time}],
    )
    created = False

    def _fake_create(self, credentials, body):
        nonlocal created
        created = True
        return {}

    monkeypatch.setattr(calendar_module.CalendarTool, "_create_event", _fake_create)
    monkeypatch.setattr(calendar_module, "Credentials", lambda **kwargs: None)

    result = await TOOL_REGISTRY["calendar"].execute(
        db_session,
        org.id,
        action="create_event",
        start_time="2026-08-18T15:00:00",
        end_time="2026-08-18T16:00:00",
    )

    assert result.success is False
    assert created is False
    assert "already booked" in result.message


async def test_org_timezone_falls_back_to_the_deployment_default(db_session: AsyncSession):
    assert await get_org_timezone(db_session, uuid.uuid4()) == "UTC"


def test_validate_arguments_drops_undeclared_fields_and_flags_missing_ones():
    tool = TOOL_REGISTRY["whatsapp"]

    safe, error = tool.validate_arguments({"to": "+15550000000", "message": "hi", "__proto__": "x", "db": "y"})
    assert error is None
    assert safe == {"to": "+15550000000", "message": "hi"}

    _, error = tool.validate_arguments({"to": "+15550000000"})
    assert error is not None

    _, error = tool.validate_arguments("not an object")
    assert error is not None
