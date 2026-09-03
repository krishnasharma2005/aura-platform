"""The demo seed has to work on a machine with no OpenAI key — it's usually the
first thing run on a fresh checkout, before credentials exist — and it has to
be safe to run twice."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed_demo import ORG_SLUG, seed
from src.agents.approvals import ApprovalStatus, ToolApproval
from src.conversations.models import Conversation, Message
from src.identity.models import Organization
from src.memory.models import KnowledgeChunk


async def _count(db: AsyncSession, model) -> int:
    return int((await db.execute(select(func.count(model.id)))).scalar_one())


async def test_seed_runs_without_an_openai_key_and_is_idempotent(db_session: AsyncSession):
    from src.core.config import get_settings

    assert not get_settings().OPENAI_API_KEY  # the test env has no key

    first = await seed(db_session)
    assert first["real_embeddings"] is False
    assert first["chunks"] > 0
    assert first["messages"] > 0

    org = (
        await db_session.execute(select(Organization).where(Organization.slug == ORG_SLUG))
    ).scalar_one()
    assert org.name == "Riverside Dental"
    assert org.public_id  # the demo widget link works out of the box

    counts_after_first = {
        "conversations": await _count(db_session, Conversation),
        "messages": await _count(db_session, Message),
        "chunks": await _count(db_session, KnowledgeChunk),
        "approvals": await _count(db_session, ToolApproval),
    }

    second = await seed(db_session)
    assert second["public_id"] == first["public_id"]  # a demo link stays valid
    assert {
        "conversations": await _count(db_session, Conversation),
        "messages": await _count(db_session, Message),
        "chunks": await _count(db_session, KnowledgeChunk),
        "approvals": await _count(db_session, ToolApproval),
    } == counts_after_first


async def test_seed_leaves_one_action_waiting_for_the_owner(db_session: AsyncSession):
    """A demo where the Approvals screen is empty doesn't show the gate at all."""
    await seed(db_session)
    pending = (
        await db_session.execute(select(ToolApproval).where(ToolApproval.status == ApprovalStatus.pending))
    ).scalars().all()
    assert len(pending) == 1
    assert pending[0].summary == "Your Receptionist wants to book an appointment on your calendar."
