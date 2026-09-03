"""Gmail tool. Shares the same Google OAuth token as calendar.py.

Like calendar.py, the Google client is synchronous, so its calls run on a
worker thread rather than blocking the event loop.

NEEDS FOUNDER INPUT: same as calendar.py — the OAuth consent flow needs a real
Google Cloud OAuth app. See docs/needs-founder-input.md.
"""

import asyncio
import base64
import uuid
from email.mime.text import MIMEText
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from src.tools.base import Tool, ToolResult
from src.tools.oauth_common import get_access_token, get_refresh_token, require_integration

GOOGLE_PROVIDER = "google"
_MAX_RESULTS_CAP = 50


class GmailTool(Tool):
    name = "gmail"
    description = "Read recent emails or send an email reply on the business's behalf."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list_recent", "send_email"]},
            "to": {"type": "string", "description": "Recipient email address (for send_email)."},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["action"],
    }

    async def execute(self, db: AsyncSession, org_id: uuid.UUID, **kwargs: Any) -> ToolResult:
        integration = await require_integration(db, org_id, GOOGLE_PROVIDER)
        credentials = Credentials(
            token=get_access_token(integration), refresh_token=get_refresh_token(integration)
        )

        action = kwargs.get("action")
        if action == "list_recent":
            max_results = kwargs.get("max_results") or 10
            if not isinstance(max_results, int) or max_results < 1:
                max_results = 10
            results = await asyncio.to_thread(
                self._list_recent, credentials, min(max_results, _MAX_RESULTS_CAP)
            )
            return ToolResult(success=True, data={"messages": results.get("messages", [])})

        if action == "send_email":
            to = kwargs.get("to")
            if not to:
                return ToolResult(success=False, message="I need to know who to send that email to.")
            sent = await asyncio.to_thread(
                self._send_email, credentials, to, kwargs.get("subject", ""), kwargs.get("body", "")
            )
            return ToolResult(success=True, data={"message_id": sent.get("id")}, message="Email sent.")

        return ToolResult(success=False, message=f"Unknown gmail action: {action}")

    @staticmethod
    def _service(credentials: Credentials):
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def _list_recent(self, credentials: Credentials, max_results: int) -> dict[str, Any]:
        service = self._service(credentials)
        return service.users().messages().list(userId="me", maxResults=max_results).execute()

    def _send_email(self, credentials: Credentials, to: str, subject: str, body: str) -> dict[str, Any]:
        service = self._service(credentials)
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return service.users().messages().send(userId="me", body={"raw": raw}).execute()
