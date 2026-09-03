"""Notifies a business owner the moment their agent has something waiting for
a decision.

The demo script this answers is "Can I see it before it sends, even if I'm in
a treatment room?" — a pending approval that only ever shows up if the owner
happens to have the dashboard open is not an answer to that question. This
module is the mechanism that makes it one, independent of which delivery
channel eventually carries it.

Design: `Notifier` is a tiny interface — `send(org_id, approval)` — so the
call site (`src/agents/approvals.py::create_pending`) never needs to know or
care how (or whether) delivery actually happens. Two implementations ship:

  * `ConsoleNotifier` — logs a structured line. This is the default and it
    always works; it's what makes "did the notification fire?" testable and
    demoable without any third-party account.
  * `EmailNotifierStub` — structured correctly for a real provider (subject,
    recipient resolution, body) but the actual send is not implemented,
    because there is no SendGrid/Postmark/etc. key configured (see
    docs/needs-founder-input.md). It logs a clear "would send" line and
    raises nothing — a missing provider key must never break the approval
    flow itself, only the delivery of the notification about it.

Selecting a notifier is one setting (`NOTIFY_CHANNEL`), read at call time
rather than cached at import time, so tests can flip it per-case.
"""

import abc
import uuid
from typing import TYPE_CHECKING, Any

from src.core.config import get_settings
from src.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - import-cycle avoidance only
    from src.agents.approvals import ToolApproval

logger = get_logger(__name__)


class Notifier(abc.ABC):
    """Anything that can tell a human "a decision is waiting for you."""

    @abc.abstractmethod
    async def send(self, org_id: uuid.UUID, approval: "ToolApproval") -> None:
        """Deliver (or log) the notification. Must never raise — a failed
        notification is a missed nudge, not a reason to fail the request that
        queued the approval in the first place. Implementations should catch
        their own delivery errors and log them."""
        raise NotImplementedError


class ConsoleNotifier(Notifier):
    """The default. Writes a structured log line an operator (or, in local
    dev, the founder watching the terminal) can see immediately. This is not
    a placeholder for a "real" notifier — it is a legitimate, always-on
    channel: every deployment has logs, not every deployment has a mail
    provider configured yet."""

    async def send(self, org_id: uuid.UUID, approval: "ToolApproval") -> None:
        logger.info(
            "approval_pending_notification",
            extra={
                "extra_fields": {
                    "org_id": str(org_id),
                    "approval_id": str(approval.id),
                    "agent_slug": approval.agent_slug,
                    "tool": approval.tool_name,
                    "summary": approval.summary,
                    "channel": "console",
                }
            },
        )


class EmailNotifierStub(Notifier):
    """Structured for a real transactional-email provider, but the actual
    send is NOT implemented — there is no provider key configured (see
    docs/needs-founder-input.md, "Notification email provider"). Turning this
    on for real is a config change (set NOTIFY_EMAIL_PROVIDER_API_KEY and
    NOTIFY_CHANNEL=email) plus filling in `_send_via_provider` — not a
    redesign: the recipient resolution, subject, and body are already correct
    below.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def _recipient(self, org_id: uuid.UUID) -> str | None:
        # A real implementation resolves the org's owner email (via the
        # `memberships`/`users` tables). Deliberately not looked up here so
        # this stub has no DB dependency — wiring that in is part of the
        # "fill in _send_via_provider" step once a provider key exists.
        return None

    def _subject(self, approval: "ToolApproval") -> str:
        return f"Needs your OK: {approval.summary}"

    def _body(self, approval: "ToolApproval") -> str:
        return (
            f"{approval.summary}\n\n"
            "Open AURA to approve or decline this before it happens:\n"
            f"{self._settings.APP_URL}/approvals\n"
        )

    async def _send_via_provider(self, recipient: str, subject: str, body: str) -> None:  # pragma: no cover
        """Not implemented. Requires NOTIFY_EMAIL_PROVIDER_API_KEY (a
        SendGrid/Postmark/etc. key) — see docs/needs-founder-input.md. Do not
        fake a successful send here."""
        raise NotImplementedError(
            "Email delivery requires a configured provider key "
            "(NOTIFY_EMAIL_PROVIDER_API_KEY) — see docs/needs-founder-input.md."
        )

    async def send(self, org_id: uuid.UUID, approval: "ToolApproval") -> None:
        if not self._settings.NOTIFY_EMAIL_PROVIDER_API_KEY:
            # Never crash the approval flow over a missing credential. Log
            # loudly (once per event, not once per app) so it's visible in
            # any environment that thinks it turned email on but didn't.
            logger.warning(
                "approval_email_notification_not_configured",
                extra={
                    "extra_fields": {
                        "org_id": str(org_id),
                        "approval_id": str(approval.id),
                        "reason": "NOTIFY_EMAIL_PROVIDER_API_KEY is not set",
                    }
                },
            )
            return

        recipient = self._recipient(org_id)  # pragma: no cover - unreachable until a key exists
        if not recipient:
            logger.warning(
                "approval_email_notification_no_recipient",
                extra={"extra_fields": {"org_id": str(org_id), "approval_id": str(approval.id)}},
            )
            return
        try:
            await self._send_via_provider(recipient, self._subject(approval), self._body(approval))
        except Exception as exc:  # pragma: no cover - never let a bad send break the caller
            logger.error("approval_email_notification_failed", exc_info=exc)


_NOTIFIERS: dict[str, type[Notifier]] = {
    "console": ConsoleNotifier,
    "email": EmailNotifierStub,
}


def get_notifier() -> Notifier:
    """Reads `NOTIFY_CHANNEL` fresh on every call (not cached at import time)
    so tests — and, later, a per-org preference — can change it without
    reloading the process. Falls back to the console notifier for any unknown
    value, since a typo'd setting should degrade to "still notifies,
    somewhere visible" rather than silently notifying no one."""
    settings = get_settings()
    channel = (getattr(settings, "NOTIFY_CHANNEL", None) or "console").lower()
    notifier_cls = _NOTIFIERS.get(channel, ConsoleNotifier)
    return notifier_cls()


async def notify_approval_pending(org_id: uuid.UUID, approval: "ToolApproval") -> None:
    """Fire-and-forget: logs a delivery failure rather than propagating it.
    Called from `src.agents.approvals.create_pending` right after the pending
    row is committed."""
    notifier = get_notifier()
    try:
        await notifier.send(org_id, approval)
    except Exception as exc:  # pragma: no cover - defense in depth; notifiers already self-guard
        logger.error("approval_notification_failed", exc_info=exc, extra={"extra_fields": {"org_id": str(org_id)}})
