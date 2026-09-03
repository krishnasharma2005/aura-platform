"""Identity domain models: User, Organization, Membership (role-based)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.db import Base


class MembershipRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Opaque, non-guessable identifier for the org's public web-chat widget
    # (POST /public/chat/{public_id}). Deliberately NOT the internal UUID and
    # NOT the slug: the slug is derived from the business name and is therefore
    # trivially guessable, and the UUID is used as a tenant key everywhere
    # else. Nullable only so pre-existing rows migrate cleanly; new orgs always
    # get one (see identity/public_id.py).
    public_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    # Lets an owner switch the public widget off without deleting the org.
    public_chat_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Captured once at onboarding to personalize agent prompts, demo/empty-state
    # copy, and the pitch narrative (see docs/customer-profile.md) — not used
    # for any access-control or billing logic.
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_goal: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # IANA timezone (e.g. "Europe/London"). Load-bearing for the calendar tool:
    # without it, "book me Tuesday at 3pm" is ambiguous and silently lands in
    # UTC. Falls back to settings.DEFAULT_TIMEZONE when unset.
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization")


class Membership(Base):
    __tablename__ = "memberships"
    # No uniqueness constraint on (user_id, organization_id) alone: a pending
    # invite may exist with user_id=NULL (invitee hasn't signed up yet), and
    # NULLs are not considered equal by SQL uniqueness checks anyway.

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id"), nullable=False
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="membership_role"), nullable=False, default=MembershipRole.member
    )
    invited_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    accepted: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    user: Mapped["User | None"] = relationship(back_populates="memberships")
    organization: Mapped["Organization"] = relationship(back_populates="memberships")
