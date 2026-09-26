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
from src.identity.deps import get_active_organization
from src.identity.models import Organization
from src.tools import google_oauth
from src.tools.google_oauth import GoogleOAuthError
from src.tools.models import Integration
from src.tools.oauth_common import get_metadata, store_integration

logger = get_logger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])

AVAILABLE_PROVIDERS = ["google", "whatsapp", "slack", "hubspot", "shopify"]


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
    status: str  # "connected" | "redirect" | "coming_soon" | "error"
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
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> IntegrationStatus:
    """Manual token-paste path: store a token an org admin already has (e.g. a
    HubSpot private app token). This is the only working connect path for
    providers other than Google — see docs/needs-founder-input.md."""
    integration = await store_integration(
        db,
        org_id=organization.id,
        provider=payload.provider,
        access_token=payload.access_token,
        refresh_token=payload.refresh_token,
        metadata=payload.metadata,
    )
    return IntegrationStatus(provider=integration.provider, connected=True, metadata=get_metadata(integration))


@router.post("/{provider}/connect", response_model=ConnectResult)
async def start_connect_flow(
    provider: str,
    organization: Organization = Depends(get_active_organization),
) -> ConnectResult:
    """One-click "Connect" from the dashboard. Google has a real OAuth consent
    redirect once GOOGLE_OAUTH_CLIENT_ID/SECRET are set; every other provider
    connects by pasting a token today (see docs/needs-founder-input.md) and
    this honestly reports "coming soon" for those rather than pretending a
    redirect flow exists."""
    if provider not in AVAILABLE_PROVIDERS:
        return ConnectResult(status="error")
    if provider == "google" and google_oauth.is_configured():
        redirect_url = await google_oauth.build_authorize_url(organization.id)
        return ConnectResult(status="redirect", redirect_url=redirect_url)
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
