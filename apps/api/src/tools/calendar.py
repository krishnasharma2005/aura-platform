"""Google Calendar tool. Reads the org's stored Google OAuth token from the
integrations table and checks availability / creates / lists / cancels events.

Two things this module is careful about:

* **Time.** Every read is anchored at "now" (`timeMin`) so the Receptionist
  sees upcoming appointments rather than the ten oldest ones in the calendar's
  history, and every write carries an explicit `timeZone` so "Tuesday at 3pm"
  means 3pm where the business actually is, not 3pm UTC.
* **Double-booking.** `check_availability` runs a real free/busy query so the
  agent can find out whether a slot is taken *before* it asks for approval to
  book it.

The google-api-python-client is synchronous (httplib2 under the hood), so every
call it makes is pushed onto a worker thread — a slow Google request must not
block the event loop and stall every other customer's request in the process.

NEEDS FOUNDER INPUT: the OAuth *consent* flow (Google Cloud OAuth app client
ID/secret, redirect URI, consent screen) is not built here — see
docs/needs-founder-input.md. This module only knows how to use an
already-stored access token; org owners connect Google Calendar for now by
pasting a token via POST /integrations."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.identity.models import Organization
from src.tools.base import Tool, ToolResult
from src.tools.oauth_common import get_access_token, get_refresh_token, require_integration

GOOGLE_PROVIDER = "google"
_MAX_EVENTS = 10


async def get_org_timezone(db: AsyncSession, org_id: uuid.UUID) -> str:
    """The business's own timezone, falling back to the deployment default."""
    result = await db.execute(select(Organization.timezone).where(Organization.id == org_id))
    return result.scalar_one_or_none() or get_settings().DEFAULT_TIMEZONE


class CalendarTool(Tool):
    name = "calendar"
    description = (
        "Check whether a time slot is free, list upcoming appointments, and create or cancel "
        "appointments on the business's Google Calendar."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["check_availability", "list_events", "create_event", "cancel_event"],
            },
            "summary": {"type": "string", "description": "Title of the appointment."},
            "start_time": {
                "type": "string",
                "description": "ISO 8601 start time, in the business's local time (e.g. 2026-08-18T15:00:00).",
            },
            "end_time": {"type": "string", "description": "ISO 8601 end time, in the business's local time."},
            "event_id": {"type": "string", "description": "Existing event id (for cancel)."},
        },
        "required": ["action"],
    }

    async def execute(self, db: AsyncSession, org_id: uuid.UUID, **kwargs: Any) -> ToolResult:
        integration = await require_integration(db, org_id, GOOGLE_PROVIDER)
        credentials = Credentials(
            token=get_access_token(integration), refresh_token=get_refresh_token(integration)
        )
        timezone = await get_org_timezone(db, org_id)

        action = kwargs.get("action")

        if action == "list_events":
            events = await asyncio.to_thread(self._list_events, credentials, timezone)
            return ToolResult(success=True, data={"events": events.get("items", [])})

        if action == "check_availability":
            start_time, end_time = kwargs.get("start_time"), kwargs.get("end_time")
            if not start_time or not end_time:
                return ToolResult(success=False, message="I need a start and end time to check that slot.")
            busy = await asyncio.to_thread(
                self._free_busy, credentials, start_time, end_time, timezone
            )
            return ToolResult(
                success=True,
                data={"available": not busy, "conflicts": busy},
                message="That time is free." if not busy else "That time is already taken.",
            )

        if action == "create_event":
            start_time, end_time = kwargs.get("start_time"), kwargs.get("end_time")
            if not start_time or not end_time:
                return ToolResult(success=False, message="I need a start and end time to book that appointment.")
            # Never book over an existing appointment, whatever the model asked for.
            busy = await asyncio.to_thread(self._free_busy, credentials, start_time, end_time, timezone)
            if busy:
                return ToolResult(
                    success=False,
                    data={"conflicts": busy},
                    message="That time is already booked. Please offer a different time.",
                )
            body = {
                "summary": kwargs.get("summary", "Appointment"),
                "start": {"dateTime": start_time, "timeZone": timezone},
                "end": {"dateTime": end_time, "timeZone": timezone},
            }
            created = await asyncio.to_thread(self._create_event, credentials, body)
            return ToolResult(success=True, data={"event": created}, message="Appointment booked.")

        if action == "cancel_event":
            event_id = kwargs.get("event_id")
            if not event_id:
                return ToolResult(success=False, message="I need to know which appointment to cancel.")
            await asyncio.to_thread(self._cancel_event, credentials, event_id)
            return ToolResult(success=True, message="Appointment cancelled.")

        return ToolResult(success=False, message=f"Unknown calendar action: {action}")

    @staticmethod
    def _service(credentials: Credentials):
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def _list_events(self, credentials: Credentials, timezone: str) -> dict[str, Any]:
        service = self._service(credentials)
        return (
            service.events()
            .list(
                calendarId="primary",
                timeMin=datetime.now(UTC).isoformat(),
                timeMax=(datetime.now(UTC) + timedelta(days=30)).isoformat(),
                maxResults=_MAX_EVENTS,
                singleEvents=True,
                orderBy="startTime",
                timeZone=timezone,
            )
            .execute()
        )

    def _free_busy(
        self, credentials: Credentials, start_time: str, end_time: str, timezone: str
    ) -> list[dict[str, Any]]:
        """Returns the busy blocks overlapping [start_time, end_time] — empty
        means the slot is free."""
        service = self._service(credentials)
        response = service.freebusy().query(
            body={
                "timeMin": start_time,
                "timeMax": end_time,
                "timeZone": timezone,
                "items": [{"id": "primary"}],
            }
        ).execute()
        return response.get("calendars", {}).get("primary", {}).get("busy", [])

    def _create_event(self, credentials: Credentials, body: dict[str, Any]) -> dict[str, Any]:
        service = self._service(credentials)
        return service.events().insert(calendarId="primary", body=body).execute()

    def _cancel_event(self, credentials: Credentials, event_id: str) -> None:
        service = self._service(credentials)
        service.events().delete(calendarId="primary", eventId=event_id).execute()
