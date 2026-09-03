"""Shared helper for reading/writing per-org integration tokens, used by every
tool adapter so the pattern isn't copy-pasted six times."""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crypto import decrypt_secret, encrypt_secret
from src.core.exceptions import ProviderNotConfiguredError
from src.tools.models import Integration

# Plain-language names shown to non-technical users when a tool isn't connected yet.
_PROVIDER_DISPLAY_NAMES = {
    "google": "Google (Calendar & Gmail)",
    "whatsapp": "WhatsApp Business",
    "slack": "Slack",
    "hubspot": "HubSpot",
    "shopify": "Shopify",
}


async def get_integration(db: AsyncSession, org_id: uuid.UUID, provider: str) -> Integration | None:
    result = await db.execute(
        select(Integration).where(Integration.org_id == org_id, Integration.provider == provider)
    )
    return result.scalar_one_or_none()


async def require_integration(db: AsyncSession, org_id: uuid.UUID, provider: str) -> Integration:
    """Returns the org's stored integration for `provider`, or raises a clean,
    user-facing error telling them to connect it first."""
    integration = await get_integration(db, org_id, provider)
    if integration is None:
        display_name = _PROVIDER_DISPLAY_NAMES.get(provider, provider.title())
        raise ProviderNotConfiguredError(f"Please connect {display_name} before using this feature.")
    return integration


async def store_integration(
    db: AsyncSession,
    org_id: uuid.UUID,
    provider: str,
    access_token: str,
    refresh_token: str | None = None,
    metadata: dict | None = None,
) -> Integration:
    """Upserts the org's stored token for `provider`."""
    integration = await get_integration(db, org_id, provider)
    metadata_json = json.dumps(metadata) if metadata else None
    stored_access = encrypt_secret(access_token)
    stored_refresh = encrypt_secret(refresh_token) if refresh_token else None
    if integration is not None:
        integration.access_token = stored_access
        integration.refresh_token = stored_refresh
        integration.metadata_json = metadata_json
    else:
        integration = Integration(
            org_id=org_id,
            provider=provider,
            access_token=stored_access,
            refresh_token=stored_refresh,
            metadata_json=metadata_json,
        )
        db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return integration


def get_access_token(integration: Integration) -> str:
    """Every tool adapter reads the org's token through here rather than off the
    model directly, so credentials are decrypted in exactly one place."""
    return decrypt_secret(integration.access_token)


def get_refresh_token(integration: Integration) -> str | None:
    return decrypt_secret(integration.refresh_token) if integration.refresh_token else None


def get_metadata(integration: Integration) -> dict:
    return json.loads(integration.metadata_json) if integration.metadata_json else {}
