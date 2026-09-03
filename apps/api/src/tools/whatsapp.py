"""WhatsApp Business Cloud API tool. Requires a stored phone_number_id + access
token per org (in the integrations table's metadata_json / access_token).

NEEDS FOUNDER INPUT: a Meta developer app + WhatsApp Business Cloud API
phone number and permanent access token. See docs/needs-founder-input.md.
"""

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.tools.base import Tool, ToolResult
from src.tools.oauth_common import get_access_token, get_metadata, require_integration

WHATSAPP_PROVIDER = "whatsapp"
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


async def send_text(db: AsyncSession, org_id: uuid.UUID, to: str, message: str) -> ToolResult:
    """Sends one text message from the org's connected WhatsApp number.

    Shared by the tool below and by the inbound webhook's reply path
    (`api/v1/public.py`), so there is exactly one place that talks to the Cloud
    API. The webhook's use is channel transport — answering a customer on the
    thread they started — not an agent-initiated outbound message, which is why
    it doesn't go through the approval gate the tool does.
    """
    integration = await require_integration(db, org_id, WHATSAPP_PROVIDER)
    phone_number_id = get_metadata(integration).get("phone_number_id")
    if not phone_number_id:
        return ToolResult(success=False, message="WhatsApp isn't fully connected yet — a phone number is missing.")

    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {get_access_token(integration)}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, headers=headers, json=payload)
    if response.status_code >= 400:
        return ToolResult(success=False, message="We couldn't send that WhatsApp message. Please try again.")
    return ToolResult(success=True, data=response.json(), message="WhatsApp message sent.")


class WhatsAppTool(Tool):
    name = "whatsapp"
    description = "Send a WhatsApp message to a customer."
    input_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Customer's WhatsApp number, E.164 format."},
            "message": {"type": "string"},
        },
        "required": ["to", "message"],
    }

    async def execute(self, db: AsyncSession, org_id: uuid.UUID, **kwargs: Any) -> ToolResult:
        return await send_text(db, org_id, to=kwargs["to"], message=kwargs["message"])
