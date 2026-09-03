"""Signed conversation tokens for the public web-chat widget.

A website visitor has no account, so the only thing that ties their second
message to their first is this token. It is signed with the application secret
and carries the organization it was issued for, which means a visitor cannot:

  * invent a conversation id and read someone else's thread (the token is
    signed — an unsigned or edited one is rejected outright), or
  * take a token issued by one business and replay it against another (the
    org is inside the signed payload and is checked against the path).
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from src.core.config import get_settings

_TOKEN_TYPE = "public_chat"


class InvalidConversationToken(Exception):
    """The token was missing, malformed, expired, or issued for another org."""


def new_conversation_key() -> str:
    """The stored conversation key for a fresh public thread. Prefixed so it's
    obvious in the database which threads came from the open internet."""
    return f"web-{secrets.token_urlsafe(18)}"


def issue(org_id: uuid.UUID, conversation_key: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "typ": _TOKEN_TYPE,
        "org": str(org_id),
        "conv": conversation_key,
        "iat": now,
        "exp": now + timedelta(hours=settings.PUBLIC_CHAT_TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def read(token: str, org_id: uuid.UUID) -> str:
    """Returns the conversation key carried by `token`, or raises."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidConversationToken("token could not be verified") from exc

    if payload.get("typ") != _TOKEN_TYPE:
        raise InvalidConversationToken("wrong token type")
    if payload.get("org") != str(org_id):
        raise InvalidConversationToken("token was issued for a different organization")
    key = payload.get("conv")
    if not isinstance(key, str) or not key:
        raise InvalidConversationToken("token carries no conversation")
    return key
