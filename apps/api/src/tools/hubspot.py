"""HubSpot CRM tool — used by Sales and Marketing agents to score leads, update
CRM records, and read pipeline data.

NEEDS FOUNDER INPUT: each customer connects their own HubSpot private app
token (or we build a HubSpot OAuth app later). See docs/needs-founder-input.md.
"""

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.tools.base import Tool, ToolResult
from src.tools.oauth_common import get_access_token, require_integration

HUBSPOT_PROVIDER = "hubspot"
HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotTool(Tool):
    name = "hubspot"
    description = "Look up, create, or update contacts/deals in the business's HubSpot CRM."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["get_contact", "update_contact", "list_deals"]},
            "email": {"type": "string", "description": "Contact email (for get_contact/update_contact)."},
            "properties": {"type": "object", "description": "Properties to set (for update_contact)."},
        },
        "required": ["action"],
    }

    async def execute(self, db: AsyncSession, org_id: uuid.UUID, **kwargs: Any) -> ToolResult:
        integration = await require_integration(db, org_id, HUBSPOT_PROVIDER)
        headers = {"Authorization": f"Bearer {get_access_token(integration)}"}
        action = kwargs.get("action")
        # `email` isn't a schema-required field (list_deals doesn't need it), so
        # it's checked here rather than assumed present.
        if action in ("get_contact", "update_contact") and not kwargs.get("email"):
            return ToolResult(success=False, message="I need the contact's email address to do that.")

        async with httpx.AsyncClient(timeout=10) as client:
            if action == "get_contact":
                response = await client.get(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/contacts/{kwargs['email']}",
                    headers=headers,
                    params={"idProperty": "email"},
                )
            elif action == "update_contact":
                response = await client.patch(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/contacts/{kwargs['email']}",
                    headers=headers,
                    params={"idProperty": "email"},
                    json={"properties": kwargs.get("properties", {})},
                )
            elif action == "list_deals":
                response = await client.get(f"{HUBSPOT_API_BASE}/crm/v3/objects/deals", headers=headers)
            else:
                return ToolResult(success=False, message=f"Unknown HubSpot action: {action}")

        if response.status_code >= 400:
            return ToolResult(success=False, message="We couldn't reach HubSpot just now. Please try again.")
        return ToolResult(success=True, data=response.json())
