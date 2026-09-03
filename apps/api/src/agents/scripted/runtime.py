"""Runs a scripted (predefined, menu-driven) agent turn.

Mirrors the parts of agents/runtime/pipeline.py::run_agent that both chat
surfaces (dashboard + public widget) rely on — persisting turns to the
durable conversation store, honoring a human takeover, publishing an audit
event — but never touches the AIGateway. It works with OPENAI_API_KEY
completely unset because it never calls it.

Temporary, by design: once an agent's config drops `chat_mode: scripted`,
its chat requests go back to run_agent unchanged. This module and
receptionist_flow.py are the only things that go away.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.runtime.pipeline import _HUMAN_CONTROLLED_NOTICE, AgentRunResult, ChatOption
from src.agents.scripted.receptionist_flow import FLOWS, START_NODE_ID
from src.conversations import service as conversation_service
from src.conversations.models import ConversationChannel
from src.events.bus import event_bus


def _node_options(node: dict) -> list[ChatOption]:
    return [ChatOption(id=o["id"], label=o["label"]) for o in node["options"]]


async def run_scripted_agent(
    db: AsyncSession,
    org_id: uuid.UUID,
    agent_slug: str,
    conversation_id: str,
    node_id: str | None = None,
    option_id: str | None = None,
    channel: ConversationChannel = ConversationChannel.dashboard,
    contact_id: uuid.UUID | None = None,
) -> AgentRunResult:
    tree = FLOWS[agent_slug]

    # A human may have taken over this thread from the dashboard (see the
    # "Take over" action) — same rule as the AI pipeline: don't auto-reply.
    existing_conversation = await conversation_service.get_conversation(db, org_id, conversation_id)
    if existing_conversation is not None and existing_conversation.mode == "human":
        turns = []
        if option_id:
            current = tree.get(node_id or START_NODE_ID, tree[START_NODE_ID])
            option = next((o for o in current["options"] if o["id"] == option_id), None)
            if option:
                turns.append(("user", option["label"], None))
        if turns:
            await conversation_service.record_turns(
                db,
                org_id=org_id,
                key=conversation_id,
                agent_slug=agent_slug,
                channel=channel,
                contact_id=contact_id,
                turns=turns,
            )
        await event_bus.publish(
            "conversation.message_held_for_human",
            {
                "org_id": org_id,
                "actor": agent_slug,
                "action": "conversation.message_held_for_human",
                "details": {"conversation_id": conversation_id, "user_message": option_id or ""},
            },
        )
        return AgentRunResult(
            response=_HUMAN_CONTROLLED_NOTICE,
            conversation_id=conversation_id,
            human_controlled=True,
            node_id=node_id or START_NODE_ID,
        )

    current_id = node_id or START_NODE_ID
    turns: list[tuple[str, str, list | None]] = []

    if option_id:
        current_node = tree.get(current_id, tree[START_NODE_ID])
        option = next((o for o in current_node["options"] if o["id"] == option_id), None)
        if option is not None:
            turns.append(("user", option["label"], None))
            current_id = option["next"]
        # An unrecognized option (stale client, tampered request) just
        # re-shows the current node rather than erroring the chat.

    node = tree.get(current_id, tree[START_NODE_ID])
    if current_id not in tree:
        current_id = START_NODE_ID

    message = node["message"]
    options = _node_options(node)
    turns.append(("assistant", message, None))

    await conversation_service.record_turns(
        db,
        org_id=org_id,
        key=conversation_id,
        agent_slug=agent_slug,
        channel=channel,
        contact_id=contact_id,
        turns=turns,
    )

    # Distinctly labeled from `agent.response_generated` so the Activity feed
    # (api/v1/audit.py::_summarize) can render an honest "Answered using the
    # guided menu" instead of implying free-form reasoning happened.
    await event_bus.publish(
        "agent.scripted_reply",
        {
            "org_id": org_id,
            "actor": agent_slug,
            "action": "agent.scripted_reply",
            "details": {
                "conversation_id": conversation_id,
                "node_id": current_id,
                "option_id": option_id,
                "response": message,
            },
        },
    )

    return AgentRunResult(
        response=message,
        conversation_id=conversation_id,
        options=options,
        node_id=current_id,
    )
