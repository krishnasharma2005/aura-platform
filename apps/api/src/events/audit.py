"""Audit log model + subscriber. Every consequential agent action is written
here via the event bus (never inline in business logic) so it's always
captured, matching the "every tool call is audited" principle. In the product
UI this is surfaced to owners as "Activity," not "Audit Log.\""""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.db import Base, async_session_factory
from src.events.bus import event_bus


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


async def _write_audit_log(payload: dict[str, Any]) -> None:
    async with async_session_factory() as session:
        session.add(
            AuditLog(
                org_id=payload["org_id"],
                actor=payload["actor"],
                action=payload["action"],
                details=payload.get("details", {}),
            )
        )
        await session.commit()


_registered = False


def register_audit_subscriber() -> None:
    """Idempotent — `create_app()` runs more than once in the test suite, and a
    duplicate subscription would write every activity entry twice."""
    global _registered
    if _registered:
        return
    for event_name in (
        "agent.response_generated",
        # The Receptionist's temporary predefined menu flow (see
        # agents/scripted/) — kept distinct so the Activity feed never
        # implies free-form reasoning happened for these turns.
        "agent.scripted_reply",
        "agent.action_approved",
        "agent.action_rejected",
        # A workflow decided something needs a person. This is what puts the
        # "Needs you" state in the Activity feed.
        "workflow.escalation_raised",
        # Conversation takeover: a human took the wheel, sent a message
        # directly, or handed control back to the agent.
        "conversation.taken_over",
        "conversation.handed_back",
        "conversation.human_message_sent",
    ):
        event_bus.subscribe(event_name, _write_audit_log)
    _registered = True
