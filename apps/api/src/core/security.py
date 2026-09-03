"""Password hashing and JWT encode/decode helpers."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from passlib.context import CryptContext

from src.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: UUID, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=30),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError subclasses on invalid/expired tokens; callers should
    translate those into AuthenticationError."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
