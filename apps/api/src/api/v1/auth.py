"""Auth routes: signup, login, refresh, and password reset."""

import uuid

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import rate_limit
from src.core.config import get_settings
from src.core.db import get_db
from src.core.exceptions import AuthenticationError, ConflictError, RateLimitedError
from src.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from src.identity import login_limits, password_reset
from src.identity.deps import get_current_user, token_predates_password_change
from src.identity.models import Membership, User
from src.identity.passwords import validate_new_password
from src.identity.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from src.notifications.mailer import send_email_safely

router = APIRouter(prefix="/auth", tags=["auth"])

_HOUR = 3600
_FORGOT_IP_LIMIT = 5
_FORGOT_EMAIL_LIMIT = 3
_RESET_IP_LIMIT = 10
FORGOT_PASSWORD_ANSWER = "If that email belongs to an account, we've sent a link to reset the password."

# A real bcrypt hash of nothing in particular. When the email isn't registered we
# still run one verification against it, so "no such account" doesn't answer
# measurably faster than "wrong password".
_dummy_hash: str | None = None


def _verify_against_nothing(password: str) -> None:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password")
    verify_password(password, _dummy_hash)


async def _allow(bucket: str, limit: int, window_seconds: int) -> bool:
    """Rate-limit check for the auth endpoints. If the limiter itself is down we
    let the request through: none of these actions need Redis to work, and locking
    everyone out because a cache is down would be the worse failure."""
    try:
        return await rate_limit.allow(bucket, limit, window_seconds)
    except rate_limit.RateLimiterUnavailable:
        return True


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    ip = rate_limit.client_ip(request)
    if not await _allow(f"signup:ip:{ip}", get_settings().AUTH_SIGNUP_IP_LIMIT, _HOUR):
        raise RateLimitedError(
            "Too many accounts were created from here recently. Please try again later.", retry_after=_HOUR
        )
    validate_new_password(payload.password)

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("An account with that email already exists.")

    user = User(email=payload.email, hashed_password=hash_password(payload.password), name=payload.name)
    db.add(user)
    await db.flush()

    # Claim any invitations sent to this address before the person had an
    # account. Without this, an invite to a not-yet-registered user is a dead
    # row: they sign up, have no membership, and every org-scoped endpoint
    # rejects them.
    pending = await db.execute(
        select(Membership).where(
            Membership.invited_email == payload.email,
            Membership.user_id.is_(None),
            Membership.accepted.is_(False),
        )
    )
    for membership in pending.scalars().all():
        membership.user_id = user.id
        membership.accepted = True

    await db.commit()
    await db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    ip = rate_limit.client_ip(request)
    await login_limits.ensure_allowed(payload.email, ip)

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None:
        _verify_against_nothing(payload.password)
    if user is None or not verify_password(payload.password, user.hashed_password):
        await login_limits.record_failure(payload.email, ip)
        raise AuthenticationError("Incorrect email or password.")

    await login_limits.clear_failures(payload.email, ip)
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Your session has expired. Please sign in again.") from exc
    if claims.get("type") != "refresh":
        raise AuthenticationError("Please sign in again.")

    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("Please sign in again.") from exc
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError("Please sign in again.")
    if token_predates_password_change(user, claims):
        raise AuthenticationError("Your password was changed. Please sign in again.")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Emails a reset link if the address has an account. The answer is identical
    either way, and the email is sent after the response, so neither the words nor
    the timing reveal whether an address is registered."""
    ip = rate_limit.client_ip(request)
    if not await _allow(f"forgot:ip:{ip}", _FORGOT_IP_LIMIT, _HOUR):
        raise RateLimitedError(
            "Too many reset requests from here. Please wait a while and try again.", retry_after=_HOUR
        )

    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    # A per-address cap, so this can't be used to flood someone's inbox. Hitting it
    # still answers the same way; it just doesn't send another email.
    email_bucket = f"forgot:email:{login_limits.digest(payload.email)}"
    if user is not None and await _allow(email_bucket, _FORGOT_EMAIL_LIMIT, _HOUR):
        token = await password_reset.issue_token(db, user)
        subject, body = password_reset.reset_email(token)
        background.add_task(send_email_safely, user.email, subject, body)
    return MessageResponse(message=FORGOT_PASSWORD_ANSWER)


@router.post("/reset-password", response_model=MessageResponse)
async def complete_password_reset(
    payload: ResetPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    ip = rate_limit.client_ip(request)
    if not await _allow(f"reset:ip:{ip}", _RESET_IP_LIMIT, _HOUR):
        raise RateLimitedError("Too many attempts from here. Please wait a while and try again.", retry_after=_HOUR)

    user = await password_reset.reset_password(db, payload.token, payload.password)
    # They've proved they own the inbox, so earlier failed sign-ins shouldn't keep
    # them out. Everyone else holding a session for this account is signed out.
    await login_limits.clear_failures(user.email, ip)
    subject, body = password_reset.password_changed_email()
    background.add_task(send_email_safely, user.email, subject, body)
    return MessageResponse(message="Your password has been changed. You can sign in now.")


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
