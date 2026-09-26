"""Google OAuth 2.0 consent flow for the "google" integration (Calendar +
Gmail share one grant — see calendar.py / gmail.py).

Built directly against Google's documented endpoints via httpx (already a
dependency, and the same pattern used by whatsapp.py/slack.py/hubspot.py's
tool adapters) rather than pulling in google-auth-oauthlib, which would be the
only consumer of that package in the codebase.

Flow:
1. `POST /integrations/google/connect` (authenticated) mints a short-lived,
   single-use `state` JWT binding this authorization attempt to the caller's
   org, and returns Google's consent-screen URL with that state attached.
2. The browser navigates there directly (not an XHR) and the user consents.
3. Google redirects the browser to `GET /integrations/google/callback` with a
   `code` + the same `state`. That request carries no Authorization header —
   the org id travels via the signed state instead — so the nonce inside it is
   checked against Redis (set in step 1, deleted here) to make the token
   single-use and reject replay.
4. The code is exchanged for tokens server-to-server and stored via the same
   `store_integration()` every other provider uses.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt

from src.core.config import get_settings
from src.core.logging import get_logger
from src.memory.short_term import get_redis

logger = get_logger(__name__)

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Calendar read/write, Gmail read + send (not gmail.modify — no need for the
# ability to delete or relabel mail the org didn't send), and the email
# address alone (to label the connection in the dashboard, nothing else).
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
]

_STATE_TTL_SECONDS = 600  # 10 minutes to complete the consent screen
_STATE_NONCE_KEY = "google_oauth_state_nonce:{nonce}"


class GoogleOAuthError(Exception):
    """Raised for any failure in the callback leg (invalid/expired/replayed
    state, or Google rejecting the code). Callers redirect the browser to the
    dashboard with a generic error flag rather than surfacing this."""


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


async def build_authorize_url(org_id: uuid.UUID) -> str:
    """Mints a single-use state token for this org and returns the full Google
    consent-screen URL to redirect the browser to."""
    settings = get_settings()
    nonce = secrets.token_urlsafe(24)
    now = datetime.now(UTC)
    state = jwt.encode(
        {
            "org_id": str(org_id),
            "nonce": nonce,
            "iat": now,
            "exp": now + timedelta(seconds=_STATE_TTL_SECONDS),
            "type": "google_oauth_state",
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    # A stolen/forged state JWT still needs its nonce present in Redis — this
    # is what makes the token single-use and rejects a replayed callback.
    await get_redis().set(_STATE_NONCE_KEY.format(nonce=nonce), str(org_id), ex=_STATE_TTL_SECONDS)

    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        # Forces Google to hand back a refresh_token on every connect, not
        # just the very first time this Google account ever consented to us.
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{httpx.QueryParams(params)}"


async def verify_state(state: str) -> uuid.UUID:
    """Decodes and single-use-verifies a state token from the callback,
    returning the org_id it was minted for. Raises GoogleOAuthError on any
    invalid, expired, or already-used state."""
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise GoogleOAuthError("Invalid or expired state token.") from exc
    if payload.get("type") != "google_oauth_state":
        raise GoogleOAuthError("Invalid state token.")

    nonce = payload.get("nonce")
    key = _STATE_NONCE_KEY.format(nonce=nonce)
    redis = get_redis()
    # GETDEL: atomically read-and-delete so two concurrent callbacks with the
    # same state (e.g. a doubled browser request) can't both succeed.
    stored_org_id = await redis.getdel(key)
    if stored_org_id is None:
        raise GoogleOAuthError("This connection link was already used or has expired.")

    try:
        return uuid.UUID(str(payload.get("org_id")))
    except (TypeError, ValueError) as exc:
        raise GoogleOAuthError("Invalid state token.") from exc


async def exchange_code(code: str) -> dict:
    """Exchanges an authorization code for tokens. Returns the raw token
    response dict (access_token, refresh_token, expires_in, ...)."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
            },
        )
    if response.status_code >= 400:
        logger.warning(
            "google_oauth_token_exchange_failed",
            extra={"extra_fields": {"status_code": response.status_code}},
        )
        raise GoogleOAuthError("Google didn't accept that connection request.")
    return response.json()


async def fetch_email(access_token: str) -> str | None:
    """Best-effort lookup of the connected account's email, purely to label
    the connection in the dashboard. Never blocks the connection on failure."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        if response.status_code >= 400:
            return None
        return response.json().get("email")
    except httpx.HTTPError:
        return None
