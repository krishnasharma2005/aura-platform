"""Auth routes: signup, login, refresh."""

import uuid

import jwt
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.exceptions import AuthenticationError, ConflictError
from src.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from src.identity.deps import get_current_user
from src.identity.models import Membership, User
from src.identity.schemas import LoginRequest, RefreshRequest, SignupRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
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
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise AuthenticationError("Incorrect email or password.")

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

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
