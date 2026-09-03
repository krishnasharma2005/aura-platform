"""Slack tool — posts internal notifications on behalf of any agent (e.g.
"a new lead came in", "an appointment needs human review").

NEEDS FOUNDER INPUT: a Slack app with a bot token (chat:write scope) installed
into each customer's workspace. See docs/needs-founder-input.md.
"""

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.tools.base import Tool, ToolResult
from src.tools.oauth_common import get_access_token, require_integration

SLACK_PROVIDER = "slack"
SLACK_API_BASE = "https://slack.com/api"


class SlackTool(Tool):
    name = "slack"
    description = "Post an internal notification message to the business's Slack workspace."
    input_schema = {
        "type": "object",
        "properties": {
            "channel": {"type": "string", "description": "Slack channel name or ID."},
            "message": {"type": "string"},
        },
        "required": ["channel", "message"],
    }

    async def execute(self, db: AsyncSession, org_id: uuid.UUID, **kwargs: Any) -> ToolResult:
        integration = await require_integration(db, org_id, SLACK_PROVIDER)
        headers = {"Authorization": f"Bearer {get_access_token(integration)}"}
        payload = {"channel": kwargs["channel"], "text": kwargs["message"]}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{SLACK_API_BASE}/chat.postMessage", headers=headers, json=payload)
        body = response.json()
        if not body.get("ok"):
            return ToolResult(success=False, message="We couldn't post that Slack message. Please try again.")
        return ToolResult(success=True, data=body, message="Slack message sent.")
