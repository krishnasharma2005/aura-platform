"""Per-org integration credential storage. One row per (org, provider). Real
OAuth consent flows are out of scope for Phase 1 (see docs/needs-founder-input.md);
for now tokens are stored directly (e.g. pasted by the org owner) or written by
a future OAuth callback."""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.db import Base


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("org_id", "provider", name="uq_integration_org_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provider-specific extra fields (e.g. WhatsApp phone_number_id, Shopify shop domain).
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
