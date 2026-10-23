"""Forgotten-password recovery: an emailed, single-use, short-lived link.

How it is kept safe:

* The link carries a random 256-bit token. Only its SHA-256 is stored, so a read
  of the database can't be turned into account takeovers.
* A token works once and expires (default 60 minutes). Asking for a new link
  retires every older one, so only the newest can be used.
* The new password is checked *before* the token is spent, so a too-short
  password doesn't burn the link and force another email.
* Spending a token is a conditional UPDATE, so two simultaneous uses can't both win.
* A reset records `password_changed_at`; any sign-in token issued before it is
  refused. Resetting after a suspected compromise therefore signs the attacker
  out too, rather than only changing what the next login needs.
* Whether an address has an account is never revealed: the endpoint answers the
  same either way (see api/v1/auth.py).
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import ValidationError
from src.core.security import hash_password
from src.identity.models import PasswordResetToken, User
from src.identity.passwords import validate_new_password

INVALID_LINK = "This reset link has expired or has already been used. Please ask for a new one."


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _retire_unused_tokens(db: AsyncSession, user_id) -> None:
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
        .values(used_at=_now())
    )


async def issue_token(db: AsyncSession, user: User) -> str:
    """Creates a reset token for `user` and returns the raw value to put in the
    email. Any earlier unused tokens for the user stop working."""
    await _retire_unused_tokens(db, user.id)
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash(token),
            expires_at=_now() + timedelta(minutes=get_settings().PASSWORD_RESET_TTL_MINUTES),
        )
    )
    await db.commit()
    return token


async def reset_password(db: AsyncSession, token: str, new_password: str) -> User:
    """Spends `token` and sets the new password. Raises ValidationError, with a
    message safe to show, for a weak password or a dead link."""
    validate_new_password(new_password)

    record = (
        await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash(token.strip())))
    ).scalar_one_or_none()
    now = _now()
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise ValidationError(INVALID_LINK)

    spent = await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.id == record.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    if spent.rowcount != 1:  # someone else used it between the check and now
        await db.rollback()
        raise ValidationError(INVALID_LINK)

    user = (await db.execute(select(User).where(User.id == record.user_id))).scalar_one()
    user.hashed_password = hash_password(new_password)
    user.password_changed_at = now
    await _retire_unused_tokens(db, user.id)
    await db.commit()
    return user


def reset_email(token: str) -> tuple[str, str]:
    """(subject, plain-text body) for the reset email."""
    settings = get_settings()
    link = f"{settings.APP_URL.rstrip('/')}/reset-password?token={token}"
    body = (
        "Someone asked to reset the password for your Mesnium account.\n\n"
        f"To choose a new password, open this link (it works once, for {settings.PASSWORD_RESET_TTL_MINUTES} "
        "minutes):\n\n"
        f"{link}\n\n"
        "If this wasn't you, you can ignore this email — your password hasn't changed.\n"
    )
    return "Reset your Mesnium password", body


def password_changed_email() -> tuple[str, str]:
    body = (
        "The password for your Mesnium account was just changed, and you've been signed out "
        "everywhere.\n\n"
        "If that was you, there's nothing to do. If it wasn't, reset your password again straight "
        "away from the sign-in page and let us know.\n"
    )
    return "Your Mesnium password was changed", body
