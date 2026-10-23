"""Integration routes: list connected/available tool integrations, store a
manually-pasted token for MVP providers, and run the real Google OAuth
consent flow (the one provider with a built redirect flow so far — see
docs/needs-founder-input.md)."""

from datetime import UTC, datetime

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.db import get_db
from src.core.logging import get_logger
from src.core.exceptions import ValidationError
from src.identity.deps import get_active_organization, require_org_role
from src.identity.models import MembershipRole, Organization
from src.tools import google_oauth
from src.tools.credentials import CREDENTIAL_PROVIDERS, verify_credentials
from src.tools.google_oauth import GoogleOAuthError
from src.tools.models import Integration
from src.tools.oauth_common import get_access_token, get_metadata, get_refresh_token, store_integration

logger = get_logger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])

AVAILABLE_PROVIDERS = ["google", "whatsapp", "slack", "hubspot", "shopify"]

# Connecting or disconnecting an app decides what agents can reach and send on
# the business's behalf, so it is an owner/admin decision — the same bar as
# approving an action. Listing stays open to any member.
_operator = require_org_role(MembershipRole.owner, MembershipRole.admin)


class ConnectIntegrationRequest(BaseModel):
    provider: str
    access_token: str
    refresh_token: str | None = None
    metadata: dict | None = None


class IntegrationStatus(BaseModel):
    provider: str
    connected: bool
    metadata: dict = {}


class ConnectResult(BaseModel):
    # "connected" | "redirect" | "needs_credentials" | "coming_soon" | "error"
    status: str
    redirect_url: str | None = None


@router.get("", response_model=list[IntegrationStatus])
async def list_integrations(
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> list[IntegrationStatus]:
    result = await db.execute(select(Integration).where(Integration.org_id == organization.id))
    connected = {row.provider: row for row in result.scalars().all()}

    return [
        IntegrationStatus(
            provider=provider,
            connected=provider in connected,
            metadata=get_metadata(connected[provider]) if provider in connected else {},
        )
        for provider in AVAILABLE_PROVIDERS
    ]


@router.post("", response_model=IntegrationStatus)
async def connect_integration(
    payload: ConnectIntegrationRequest,
    organization: Organization = Depends(_operator),
    db: AsyncSession = Depends(get_db),
) -> IntegrationStatus:
    """Connect an app by pasting its key.

    For WhatsApp, Slack, HubSpot and Shopify the key is checked against the other
    app first (see tools/credentials.py) and only saved if it works; only the
    whitelisted, non-secret details that check returns are stored alongside it.
    Other providers keep the original behaviour (store what was sent) — Google
    normally connects through its own sign-in instead."""
    if payload.provider not in AVAILABLE_PROVIDERS:
        raise ValidationError("That app can't be connected yet.")

    metadata = payload.metadata
    if payload.provider in CREDENTIAL_PROVIDERS:
        verified = await verify_credentials(payload.provider, payload.access_token, payload.metadata)
        metadata = {
            **verified.metadata,
            "connected_at": datetime.now(UTC).isoformat(),
            "account_label": verified.account_label,
        }

    integration = await store_integration(
        db,
        org_id=organization.id,
        provider=payload.provider,
        access_token=payload.access_token.strip(),
        refresh_token=payload.refresh_token,
        metadata=metadata,
    )
    return IntegrationStatus(provider=integration.provider, connected=True, metadata=get_metadata(integration))


@router.delete("/{provider}", status_code=204)
async def disconnect_integration(
    provider: str,
    organization: Organization = Depends(_operator),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Forget the stored credentials. Agents lose access immediately; anything
    they had queued for approval stays queued and will simply fail if approved.
    Idempotent — disconnecting something that isn't connected is not an error."""
    if provider not in AVAILABLE_PROVIDERS:
        raise ValidationError("That app can't be disconnected.")
    result = await db.execute(
        select(Integration).where(Integration.org_id == organization.id, Integration.provider == provider)
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        return None

    if provider == "google":
        # Best effort: also tell Google to revoke the grant, so the app disappears
        # from the owner's Google account permissions and not just from ours.
        await google_oauth.revoke(get_refresh_token(integration) or get_access_token(integration))

    await db.delete(integration)
    await db.commit()
    return None


@router.post("/{provider}/connect", response_model=ConnectResult)
async def start_connect_flow(
    provider: str,
    organization: Organization = Depends(get_active_organization),
) -> ConnectResult:
    """What the dashboard's "Connect" button should do for a provider: Google
    redirects into its consent screen once GOOGLE_OAUTH_CLIENT_ID/SECRET are
    set; WhatsApp, Slack, HubSpot and Shopify ask for a key
    ("needs_credentials"); anything else honestly reports "coming soon"."""
    if provider not in AVAILABLE_PROVIDERS:
        return ConnectResult(status="error")
    if provider == "google" and google_oauth.is_configured():
        redirect_url = await google_oauth.build_authorize_url(organization.id)
        return ConnectResult(status="redirect", redirect_url=redirect_url)
    if provider in CREDENTIAL_PROVIDERS:
        # No sign-in redirect for these: the dashboard asks for the key itself.
        return ConnectResult(status="needs_credentials")
    return ConnectResult(status="coming_soon")


@router.get("/google/callback")
async def google_oauth_callback(request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """Google redirects the browser here after consent. No Authorization
    header travels with this request — the org id is recovered from the
    signed, single-use `state` param minted by start_connect_flow above."""
    settings = get_settings()
    dashboard_integrations_url = f"{settings.APP_URL}/settings/integrations"

    if request.query_params.get("error"):
        return RedirectResponse(f"{dashboard_integrations_url}?google_connect=denied")

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return RedirectResponse(f"{dashboard_integrations_url}?google_connect=error")

    try:
        org_id = await google_oauth.verify_state(state)
        tokens = await google_oauth.exchange_code(code)
    except GoogleOAuthError as exc:
        logger.warning("google_oauth_callback_failed", extra={"extra_fields": {"reason": str(exc)}})
        return RedirectResponse(f"{dashboard_integrations_url}?google_connect=error")

    access_token = tokens.get("access_token")
    if not access_token:
        return RedirectResponse(f"{dashboard_integrations_url}?google_connect=error")

    email = await google_oauth.fetch_email(access_token)
    await store_integration(
        db,
        org_id=org_id,
        provider="google",
        access_token=access_token,
        refresh_token=tokens.get("refresh_token"),
        metadata={
            "connected_at": datetime.now(UTC).isoformat(),
            "account_label": email,
        },
    )
    return RedirectResponse(f"{dashboard_integrations_url}?google_connect=success")
