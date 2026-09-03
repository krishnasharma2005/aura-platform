"""Public, unauthenticated inbound channels.

This is the thing a business embeds on its own website: a customer types a
question, the org's Receptionist answers. It is the only surface in AURA that
anyone on the internet can reach, so the rules it plays by are stricter than
anywhere else:

  * The organization is addressed by an opaque, non-guessable `public_id` —
    never the internal UUID (a tenant key elsewhere) and never the slug (which
    is derived from the business name, so it's guessable by anyone who knows
    the business exists).
  * Every request is rate limited per IP and per conversation, the message
    length is capped, and a conversation stops accepting messages once it gets
    implausibly long. All three are cost and abuse controls.
  * It runs through the *same* `run_agent` runtime as the dashboard — no
    parallel code path — so the server-side approval gate applies unchanged: a
    website visitor can make the agent *ask* to book or cancel an appointment,
    and it lands in the owner's approval queue exactly like any other request.
    It cannot make the action happen.
  * The visitor's message is marked as untrusted external content before it
    reaches the model (see `_EXTERNAL_CHANNELS` in the runtime).
  * Nothing internal is ever returned: not the org's name/id, not which tools
    exist, not pending approvals, not provider errors. A failure is one plain
    apologetic sentence.
"""

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.runtime.loader import load_agent_config
from src.agents.runtime.pipeline import ChatOption, run_agent
from src.agents.scripted.runtime import run_scripted_agent
from src.ai_gateway.gateway import AIGateway
from src.conversations import public_token, service as conversation_service
from src.conversations.models import ConversationChannel
from src.core import rate_limit
from src.core.config import get_settings
from src.core.db import get_db
from src.core.exceptions import AuraError, NotFoundError
from src.core.logging import get_logger
from src.events.bus import event_bus
from src.identity.models import Organization
from src.tools.oauth_common import get_metadata
from src.tools.models import Integration

logger = get_logger(__name__)

router = APIRouter(prefix="/public", tags=["public"])

RECEPTIONIST_SLUG = "receptionist"

# Every visitor-facing failure message. Deliberately identical in shape whether
# the cause was a missing org, a disabled widget, or an unconfigured AI
# provider — the visitor learns nothing about the business's setup either way.
_UNAVAILABLE = "Sorry — our chat isn't available right now. Please try again shortly."
_NOT_AVAILABLE_HERE = "Sorry — this chat isn't available."
_TOO_MANY = "You're sending messages a bit too quickly. Please wait a moment and try again."
_TOO_LONG_CONVERSATION = (
    "This chat has gone on for a while. Please start a new one, or contact the team directly."
)


async def _publish_inbound(
    org_id: Any,
    conversation_key: str,
    channel: str,
    message: str,
    contact_phone: str | None = None,
    contact_name: str | None = None,
) -> None:
    """Announces "a member of the public just said something" on the event bus.

    Event-triggered workflows subscribe to this (see
    `src/workflows/runner.py`); the escalation template uses it to notice an
    enquiry nobody answered. Publishing is fire-and-forget by design — the bus
    logs handler failures and a workflow must never be able to break the
    customer's chat.
    """
    await event_bus.publish(
        "conversation.message_received",
        {
            "org_id": org_id,
            "conversation_key": conversation_key,
            "channel": channel,
            "last_message": message[:500],
            "contact_phone": contact_phone,
            "contact_name": contact_name,
        },
    )


class TooManyRequestsError(AuraError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_message = _TOO_MANY


class MessageTooLongError(AuraError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    default_message = "That message is a bit too long. Please shorten it and send it again."


class ConversationFullError(AuraError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_message = _TOO_LONG_CONVERSATION


class ChatUnavailableError(AuraError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_message = _UNAVAILABLE


class PublicChatRequest(BaseModel):
    # Only required for the real AI-driven pipeline (enforced below, not by
    # min_length) — a scripted-flow request to fetch the opening menu, or to
    # pick an option, sends no free text at all.
    message: str = ""
    conversation_token: str | None = None
    # Scripted-flow-only fields (agents/scripted/), ignored by the AI
    # pipeline. See ChatRequest in api/v1/agents.py for the same shape.
    node_id: str | None = None
    option_id: str | None = None


class PublicChatStatusResponse(BaseModel):
    """Whether the embeddable widget should render itself at all. Always 200,
    and `available` is the only field — the same non-answer for "no such
    business", "chat is switched off", and any lookup error, so a website
    visitor's browser (or anyone poking at this endpoint directly) learns
    nothing about which public ids exist or why one doesn't work."""

    available: bool


class PublicChatResponse(BaseModel):
    """Nothing here identifies the business or its internals — just the reply
    and the token needed to continue the thread."""

    reply: str
    conversation_token: str
    # Populated only for a scripted (predefined, menu-driven) reply — see
    # agents/scripted/. Empty/None for a real AI-driven response, so an older
    # widget build that doesn't know about these fields keeps working
    # unchanged.
    options: list[ChatOption] = []
    node_id: str | None = None


def get_gateway() -> AIGateway:
    return AIGateway()


def _client_ip(request: Request) -> str:
    """X-Forwarded-For is trivially forgeable, so it's only honoured when the
    deployment says it sits behind a proxy that overwrites it. Otherwise the
    per-IP limit would be one header away from useless."""
    settings = get_settings()
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _within_limit(bucket: str, limit: int, window_seconds: int) -> bool:
    """A limiter outage is our problem, not the visitor's — it still refuses
    the request, but with the generic apology rather than by telling a customer
    they're sending messages too quickly."""
    try:
        return await rate_limit.allow(bucket, limit, window_seconds)
    except rate_limit.RateLimiterUnavailable as exc:
        raise ChatUnavailableError() from exc


async def _resolve_org(db: AsyncSession, org_public_id: str) -> Organization:
    result = await db.execute(select(Organization).where(Organization.public_id == org_public_id))
    org = result.scalar_one_or_none()
    if org is None or not org.public_chat_enabled:
        # Same answer for "no such business" and "switched off" — an outsider
        # should not be able to probe which public ids exist.
        raise NotFoundError(_NOT_AVAILABLE_HERE)
    return org


@router.get("/chat/{org_public_id}/status", response_model=PublicChatStatusResponse)
async def public_chat_status(org_public_id: str, db: AsyncSession = Depends(get_db)) -> PublicChatStatusResponse:
    """Lets the embed script decide whether to render the bubble at all,
    without ever attempting a real chat turn just to find out. Deliberately
    not rate-limited as tightly as the chat endpoint itself — it does no work
    beyond one lookup — but it's still a read-only, side-effect-free check
    that reveals nothing beyond a boolean."""
    result = await db.execute(select(Organization).where(Organization.public_id == org_public_id))
    org = result.scalar_one_or_none()
    return PublicChatStatusResponse(available=bool(org and org.public_chat_enabled))


@router.post("/chat/{org_public_id}", response_model=PublicChatResponse)
async def public_chat(
    org_public_id: str,
    payload: PublicChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    gateway: AIGateway = Depends(get_gateway),
) -> PublicChatResponse:
    settings = get_settings()

    # Rate limit by IP before touching the database, so an unknown public id
    # can't be used to hammer the org lookup.
    if not await _within_limit(
        f"public_chat:ip:{_client_ip(request)}",
        settings.PUBLIC_CHAT_IP_LIMIT,
        settings.PUBLIC_CHAT_IP_WINDOW_SECONDS,
    ):
        raise TooManyRequestsError()

    org = await _resolve_org(db, org_public_id)

    # Temporary: the Receptionist runs a predefined menu flow instead of the
    # real AI pipeline while OPENAI_API_KEY is unset (agents/scripted/,
    # agents/configs/receptionist.yaml). A scripted request can legitimately
    # carry no free text at all (fetching the opening menu, picking an
    # option), so the "must type something" rule only applies to the AI path.
    config = load_agent_config(RECEPTIONIST_SLUG)
    scripted = config.chat_mode == "scripted"

    message = payload.message.strip()
    if not scripted and not message:
        raise MessageTooLongError("Please type a message first.")
    if len(message) > settings.PUBLIC_CHAT_MAX_MESSAGE_CHARS:
        raise MessageTooLongError()

    if payload.conversation_token:
        try:
            conversation_key = public_token.read(payload.conversation_token, org.id)
        except public_token.InvalidConversationToken:
            # Don't explain why. Start them a clean thread instead of leaking
            # whether the token was expired, forged, or another org's.
            conversation_key = public_token.new_conversation_key()
    else:
        conversation_key = public_token.new_conversation_key()

    if not await _within_limit(
        f"public_chat:conv:{org.id}:{conversation_key}",
        settings.PUBLIC_CHAT_CONVERSATION_LIMIT,
        settings.PUBLIC_CHAT_CONVERSATION_WINDOW_SECONDS,
    ):
        raise TooManyRequestsError()

    existing = await conversation_service.get_conversation(db, org.id, conversation_key)
    if existing is not None:
        if existing.channel is not ConversationChannel.web_chat:
            # A signed token should never point at a dashboard thread, but if
            # one somehow did, a visitor must not be able to read or continue
            # the owner's own conversation.
            raise NotFoundError(_NOT_AVAILABLE_HERE)
        if await conversation_service.count_messages(db, existing) >= settings.PUBLIC_CHAT_MAX_MESSAGES:
            raise ConversationFullError()

    if scripted:
        # Never touches the AI Gateway — see agents/scripted/runtime.py.
        result = await run_scripted_agent(
            db=db,
            org_id=org.id,
            agent_slug=RECEPTIONIST_SLUG,
            conversation_id=conversation_key,
            node_id=payload.node_id,
            option_id=payload.option_id,
            channel=ConversationChannel.web_chat,
        )
        if message or payload.option_id:
            await _publish_inbound(org.id, conversation_key, "web_chat", message or payload.option_id or "")
        return PublicChatResponse(
            reply=result.response,
            conversation_token=public_token.issue(org.id, conversation_key),
            options=result.options,
            node_id=result.node_id,
        )

    try:
        result = await run_agent(
            db=db,
            gateway=gateway,
            org_id=org.id,
            agent_slug=RECEPTIONIST_SLUG,
            conversation_id=conversation_key,
            user_message=message,
            channel=ConversationChannel.web_chat,
        )
    except Exception as exc:
        # Everything — a provider outage, a permission error naming a tool, a
        # bug — becomes one apologetic sentence. Internal detail goes to the
        # logs, never to the visitor.
        # Read the id before rolling back: the rollback expires the loaded
        # Organization, and touching it afterwards would try to reload it.
        org_id = org.id
        logger.error(
            "public_chat_failed",
            exc_info=exc,
            extra={"extra_fields": {"org_id": str(org_id), "conversation": conversation_key}},
        )
        # "What if it breaks and I lose a lead?" is a live sales objection. The
        # answer has to be that we don't: the enquiry is stored even when the
        # reply failed, and the event below lets the escalation workflow find
        # it and put it in front of a human.
        try:
            await db.rollback()
            await conversation_service.record_turns(
                db,
                org_id=org_id,
                key=conversation_key,
                agent_slug=RECEPTIONIST_SLUG,
                channel=ConversationChannel.web_chat,
                turns=[("user", message, None)],
            )
            await _publish_inbound(org_id, conversation_key, "web_chat", message)
        except Exception:  # pragma: no cover - never let salvage hide the original failure
            logger.error("public_chat_salvage_failed", extra={"extra_fields": {"org_id": str(org_id)}})
        raise ChatUnavailableError() from exc

    await _publish_inbound(org.id, conversation_key, "web_chat", message)

    # `result.pending_approvals` is intentionally dropped: the visitor is told
    # by the agent's own wording that something is awaiting confirmation, and
    # is never shown the owner's approval queue.
    return PublicChatResponse(
        reply=result.response,
        conversation_token=public_token.issue(org.id, conversation_key),
    )


# ---------------------------------------------------------------------------
# WhatsApp inbound webhook (Meta Cloud API)
#
# NOT VERIFIABLE END TO END without founder credentials — it needs a Meta
# developer app, a WhatsApp Business phone number, an app secret and a public
# HTTPS callback URL. See docs/needs-founder-input.md §10. The handshake and
# signature checks below are implemented to Meta's spec so that turning it on
# is a configuration step, not a build step.
# ---------------------------------------------------------------------------


@router.get("/whatsapp/webhook")
async def verify_whatsapp_webhook(request: Request) -> Response:
    """Meta's subscription handshake: it GETs the callback URL with
    hub.mode/hub.verify_token/hub.challenge and expects the raw challenge
    echoed back as plain text when the token matches."""
    settings = get_settings()
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    if not settings.WHATSAPP_VERIFY_TOKEN:
        logger.warning("whatsapp_webhook_verify_not_configured")
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    if mode != "subscribe" or not hmac.compare_digest(token or "", settings.WHATSAPP_VERIFY_TOKEN):
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    return Response(content=challenge, media_type="text/plain")


def _signature_is_valid(app_secret: str, raw_body: bytes, header: str | None) -> bool:
    """Meta signs the raw request body with the app secret and sends it as
    `X-Hub-Signature-256: sha256=<hex>`. The comparison is constant-time, and
    the *raw* bytes are used — re-serializing the parsed JSON would not
    reproduce the same digest."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


async def _org_for_phone_number_id(db: AsyncSession, phone_number_id: str) -> Organization | None:
    """Maps the inbound WhatsApp business number back to the organization that
    connected it. Each org stores its own phone_number_id in its integration
    metadata, so this is how a shared webhook stays multi-tenant."""
    rows = (
        await db.execute(select(Integration).where(Integration.provider == "whatsapp"))
    ).scalars().all()
    for integration in rows:
        if get_metadata(integration).get("phone_number_id") == phone_number_id:
            result = await db.execute(select(Organization).where(Organization.id == integration.org_id))
            return result.scalar_one_or_none()
    return None


def _extract_messages(body: dict[str, Any]) -> list[tuple[str, str, str, str | None]]:
    """Flattens Meta's nested webhook payload into
    (phone_number_id, from_number, text, profile_name) tuples. Only plain text
    messages are handled; media/status callbacks are ignored."""
    extracted: list[tuple[str, str, str, str | None]] = []
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            phone_number_id = ((value.get("metadata") or {}).get("phone_number_id")) or ""
            names = {
                (contact.get("wa_id") or ""): ((contact.get("profile") or {}).get("name"))
                for contact in (value.get("contacts") or [])
            }
            for message in value.get("messages") or []:
                if message.get("type") != "text":
                    continue
                text = ((message.get("text") or {}).get("body") or "").strip()
                sender = message.get("from") or ""
                if not text or not sender or not phone_number_id:
                    continue
                extracted.append((phone_number_id, sender, text, names.get(sender)))
    return extracted


@router.post("/whatsapp/webhook")
async def receive_whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    gateway: AIGateway = Depends(get_gateway),
) -> Response:
    """Inbound customer messages. Always answers 200 once the signature checks
    out: Meta retries anything else, and a retry storm caused by our own bug
    would multiply every failure."""
    settings = get_settings()
    raw_body = await request.body()

    if not settings.WHATSAPP_APP_SECRET:
        logger.warning("whatsapp_webhook_not_configured")
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    if not _signature_is_valid(
        settings.WHATSAPP_APP_SECRET, raw_body, request.headers.get("x-hub-signature-256")
    ):
        logger.warning("whatsapp_webhook_bad_signature")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        body = json.loads(raw_body or b"{}")
    except ValueError:
        return Response(status_code=status.HTTP_200_OK)

    for phone_number_id, sender, text, profile_name in _extract_messages(body):
        try:
            await _handle_whatsapp_message(db, gateway, phone_number_id, sender, text, profile_name)
        except Exception as exc:
            logger.error("whatsapp_inbound_failed", exc_info=exc)

    return Response(status_code=status.HTTP_200_OK)


async def _handle_whatsapp_message(
    db: AsyncSession,
    gateway: AIGateway,
    phone_number_id: str,
    sender: str,
    text: str,
    profile_name: str | None,
) -> None:
    org = await _org_for_phone_number_id(db, phone_number_id)
    if org is None:
        logger.warning("whatsapp_inbound_unknown_number")
        return

    settings = get_settings()
    if len(text) > settings.PUBLIC_CHAT_MAX_MESSAGE_CHARS:
        text = text[: settings.PUBLIC_CHAT_MAX_MESSAGE_CHARS]

    contact = await conversation_service.upsert_contact(db, org.id, name=profile_name, phone=sender)
    await db.commit()

    conversation_key = f"whatsapp-{sender}"
    result = await run_agent(
        db=db,
        gateway=gateway,
        org_id=org.id,
        agent_slug=RECEPTIONIST_SLUG,
        conversation_id=conversation_key,
        user_message=text,
        channel=ConversationChannel.whatsapp,
        contact_id=contact.id,
    )

    # Replying on the customer's own thread is the channel transport, not an
    # agent-initiated outbound message, so it isn't approval-gated — anything
    # consequential the agent wanted to *do* still queued for the owner.
    # Exception: while a human has taken this conversation over, nothing is
    # auto-sent — the owner is the one replying now, through the "Take over"
    # message endpoint, and an automatic "we'll get back to you" alongside a
    # human's real reply would be confusing at best.
    if not result.human_controlled:
        from src.tools.whatsapp import send_text

        await send_text(db, org.id, to=sender, message=result.response)

    await _publish_inbound(
        org.id, conversation_key, "whatsapp", text, contact_phone=sender, contact_name=profile_name
    )
