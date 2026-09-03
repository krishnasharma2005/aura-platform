"""Long-term memory: durable org+agent-scoped facts stored in Postgres."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.memory.models import MemoryFact


async def upsert_fact(db: AsyncSession, org_id: uuid.UUID, agent_id: str, key: str, value: str) -> MemoryFact:
    result = await db.execute(
        select(MemoryFact).where(
            MemoryFact.org_id == org_id, MemoryFact.agent_id == agent_id, MemoryFact.key == key
        )
    )
    fact = result.scalar_one_or_none()
    if fact is not None:
        fact.value = value
    else:
        fact = MemoryFact(org_id=org_id, agent_id=agent_id, key=key, value=value)
        db.add(fact)
    await db.commit()
    await db.refresh(fact)
    return fact


async def get_facts(db: AsyncSession, org_id: uuid.UUID, agent_id: str) -> list[MemoryFact]:
    result = await db.execute(
        select(MemoryFact).where(MemoryFact.org_id == org_id, MemoryFact.agent_id == agent_id)
    )
    return list(result.scalars().all())


async def get_fact(db: AsyncSession, org_id: uuid.UUID, agent_id: str, key: str) -> MemoryFact | None:
    result = await db.execute(
        select(MemoryFact).where(
            MemoryFact.org_id == org_id, MemoryFact.agent_id == agent_id, MemoryFact.key == key
        )
    )
    return result.scalar_one_or_none()
