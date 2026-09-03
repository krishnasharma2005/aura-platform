"""Integration routes: list connected/available tool integrations, and store a
manually-pasted token for MVP (the real OAuth consent flow is a
"needs founder input" item — see docs/needs-founder-input.md)."""

from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.identity.deps import get_active_organization
from src.identity.models import Organization
from src.tools.models import Integration
from src.tools.oauth_common import get_metadata, store_integration

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
    status: str  # "connected" | "coming_soon" | "error"
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
    HubSpot private app token). This is the only working connect path until
    the OAuth consent flows below exist — see docs/needs-founder-input.md."""
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
async def start_connect_flow(provider: str) -> ConnectResult:
    """One-click "Connect" from the dashboard. None of these providers has a
    real OAuth consent app configured yet (that needs founder-supplied
    credentials — see docs/needs-founder-input.md), so this honestly reports
    "coming soon" for every provider rather than pretending to succeed. Once
    an OAuth app exists for a provider, this becomes the place that returns a
    real redirect_url into that provider's consent screen."""
    if provider not in AVAILABLE_PROVIDERS:
        return ConnectResult(status="error")
    return ConnectResult(status="coming_soon")
