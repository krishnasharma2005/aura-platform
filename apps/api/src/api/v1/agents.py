"""Agent routes: list available agents for an org, chat with an agent, and
read conversation history (short-term memory)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.runtime.loader import AgentNotFoundError, list_agent_configs, load_agent_config
from src.agents.runtime.pipeline import AgentRunResult, run_agent
from src.agents.scripted.runtime import run_scripted_agent
from src.ai_gateway.gateway import AIGateway
from src.conversations import service as conversation_service
from src.core.db import get_db
from src.core.exceptions import NotFoundError
from src.identity.deps import get_active_organization
from src.identity.models import Organization
from src.memory.short_term import get_turns

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentSummary(BaseModel):
    """What the dashboard needs to render an agent card. Deliberately excludes
    `system_prompt` and `allowed_tools`: shipping those to the browser hands
    anyone a map of the prompt-injection surface and the exact tool allowlist."""

    slug: str
    display_name: str
    description: str | None = None


class ChatRequest(BaseModel):
    conversation_id: str
    # Optional so a scripted (predefined, menu-driven) turn can be sent with
    # no free-text at all — see node_id/option_id below and
    # agents/scripted/runtime.py. Still required in practice for the real
    # AI-driven pipeline, which needs something to answer.
    message: str = ""
    # Scripted-flow-only fields (agents/scripted/). `node_id` is the node the
    # caller is currently on (omit for a brand-new conversation to get the
    # opening menu); `option_id` is which of that node's options was picked.
    # Both are ignored by the real AI pipeline.
    node_id: str | None = None
    option_id: str | None = None


class ConversationTurn(BaseModel):
    """One stored turn. `tool_calls` and `created_at` are additive — a turn
    replayed from the Redis working set (pre-persistence conversations) has
    neither."""

    role: str
    content: str
    tool_calls: list[Any] = []
    created_at: datetime | None = None


def get_gateway() -> AIGateway:
    return AIGateway()


@router.get("", response_model=list[AgentSummary])
async def list_agents(organization: Organization = Depends(get_active_organization)) -> list[AgentSummary]:
    return [
        AgentSummary(slug=config.slug, display_name=config.display_name, description=config.description)
        for config in list_agent_configs()
    ]


@router.post("/{slug}/chat", response_model=AgentRunResult)
async def chat_with_agent(
    slug: str,
    payload: ChatRequest,
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
    gateway: AIGateway = Depends(get_gateway),
) -> AgentRunResult:
    try:
        config = load_agent_config(slug)
    except AgentNotFoundError as exc:
        raise NotFoundError("That assistant doesn't exist.") from exc

    if config.chat_mode == "scripted":
        return await run_scripted_agent(
            db=db,
            org_id=organization.id,
            agent_slug=slug,
            conversation_id=payload.conversation_id,
            node_id=payload.node_id,
            option_id=payload.option_id,
        )

    return await run_agent(
        db=db,
        gateway=gateway,
        org_id=organization.id,
        agent_slug=slug,
        conversation_id=payload.conversation_id,
        user_message=payload.message,
    )


@router.get("/{slug}/conversations/{conversation_id}", response_model=list[ConversationTurn])
async def get_conversation_history(
    slug: str,
    conversation_id: str,
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationTurn]:
    """Reads the durable transcript, falling back to the Redis working set for
    a conversation that predates persistence. Always org-scoped: a conversation
    id from another tenant resolves to an empty history, never to their data."""
    try:
        load_agent_config(slug)  # validates the agent exists
    except AgentNotFoundError as exc:
        raise NotFoundError("That assistant doesn't exist.") from exc

    stored = await conversation_service.get_turns(db, organization.id, conversation_id)
    if stored:
        return [ConversationTurn(**turn) for turn in stored]

    return [
        ConversationTurn(role=turn["role"], content=turn["content"])
        for turn in await get_turns(str(organization.id), conversation_id)
    ]
