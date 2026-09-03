"""Pydantic request/response schemas for the identity module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from src.identity.models import MembershipRole


def _normalize_email(value: str) -> str:
    # Email addresses are treated case-insensitively everywhere (uniqueness,
    # login, invite matching), so normalize once at the request boundary.
    return value.lower()


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str

    _normalize = field_validator("email")(_normalize_email)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    _normalize = field_validator("email")(_normalize_email)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime


class OrganizationCreateRequest(BaseModel):
    name: str
    business_type: str | None = None
    primary_goal: str | None = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    business_type: str | None = None
    # The opaque id used by the embeddable public web-chat widget
    # (POST /api/v1/public/chat/{public_id}). Safe to show the owner — that's
    # the point — but it is not a secret to log or share casually.
    public_id: str | None = None
    public_chat_enabled: bool = True
    created_at: datetime


class InviteRequest(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.member

    _normalize = field_validator("email")(_normalize_email)


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID
    role: MembershipRole
    invited_email: str | None = None
    accepted: bool
    created_at: datetime
