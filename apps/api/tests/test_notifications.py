"""Approval notifications: a pending approval must fire a notification the
moment it's created, not only when the owner happens to open the dashboard.

The console notifier is the default and always-on path (no credentials
needed); the email notifier is a documented stub that must never pretend to
send when no provider key is configured.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import approvals as approvals_service
from src.core.config import get_settings
from src.notifications import notifier as notifier_module
from src.notifications.notifier import ConsoleNotifier, EmailNotifierStub, get_notifier


async def _pending(db: AsyncSession, org_id: uuid.UUID) -> "approvals_service.ToolApproval":
    return await approvals_service.create_pending(
        db,
        org_id=org_id,
        agent_slug="receptionist",
        agent_display_name="Receptionist",
        conversation_id="conv-1",
        tool_name="calendar",
        arguments={"action": "create_event"},
    )


def test_default_notifier_is_console(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("NOTIFY_CHANNEL", raising=False)
    assert isinstance(get_notifier(), ConsoleNotifier)
    get_settings.cache_clear()


def test_unknown_channel_falls_back_to_console(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NOTIFY_CHANNEL", "carrier-pigeon")
    assert isinstance(get_notifier(), ConsoleNotifier)
    get_settings.cache_clear()
    monkeypatch.delenv("NOTIFY_CHANNEL", raising=False)


async def test_creating_a_pending_approval_fires_a_notification(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    _, org, _ = user_and_org
    sent = AsyncMock()
    monkeypatch.setattr(notifier_module, "get_notifier", lambda: _FakeNotifier(sent))

    approval = await _pending(db_session, org.id)

    sent.assert_awaited_once()
    call_org_id, call_approval = sent.await_args.args
    assert call_org_id == org.id
    assert call_approval.id == approval.id


async def test_notification_failure_does_not_break_approval_creation(
    db_session: AsyncSession, user_and_org, monkeypatch
):
    """A dead mail provider must never be the reason a pending approval fails
    to be created — the approval is the thing that matters."""
    _, org, _ = user_and_org

    class _BoomNotifier:
        async def send(self, org_id, approval):
            raise RuntimeError("provider is down")

    monkeypatch.setattr(notifier_module, "get_notifier", lambda: _BoomNotifier())

    approval = await _pending(db_session, org.id)
    assert approval.id is not None


async def test_console_notifier_logs_without_raising(db_session: AsyncSession, user_and_org):
    _, org, _ = user_and_org
    approval = await _pending(db_session, org.id)
    # Doesn't raise — this is the whole contract for the default notifier.
    await ConsoleNotifier().send(org.id, approval)


async def test_email_notifier_noops_without_a_provider_key(db_session: AsyncSession, user_and_org, monkeypatch):
    """The email notifier must never fake a send when no provider key is
    configured — it should log and return, not raise, not pretend."""
    get_settings.cache_clear()
    monkeypatch.delenv("NOTIFY_EMAIL_PROVIDER_API_KEY", raising=False)
    _, org, _ = user_and_org
    approval = await _pending(db_session, org.id)

    email_notifier = EmailNotifierStub()
    send_via_provider = AsyncMock()
    email_notifier._send_via_provider = send_via_provider  # type: ignore[method-assign]

    await email_notifier.send(org.id, approval)

    send_via_provider.assert_not_awaited()
    get_settings.cache_clear()


class _FakeNotifier:
    def __init__(self, sent: AsyncMock):
        self._sent = sent

    async def send(self, org_id, approval):
        await self._sent(org_id, approval)
