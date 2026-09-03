"""Semantic (vector) memory: pgvector-backed search over knowledge_chunks.
Requires real Postgres with the pgvector extension — the cosine-distance `<=>`
operator used here has no sqlite equivalent, so this module is exercised
against Postgres only (see tests/conftest.py for the sqlite fallback used by
the rest of the test suite)."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.memory.models import KnowledgeChunk


async def add_chunk(db: AsyncSession, org_id: uuid.UUID, source: str, content: str, embedding: list[float]) -> KnowledgeChunk:
    chunk = KnowledgeChunk(org_id=org_id, source=source, content=content, embedding=embedding)
    db.add(chunk)
    await db.commit()
    await db.refresh(chunk)
    return chunk


async def add_chunks(
    db: AsyncSession, org_id: uuid.UUID, source: str, chunks: list[tuple[str, list[float]]]
) -> list[KnowledgeChunk]:
    """Stores a whole document's chunks in one transaction. Committing per
    chunk (the previous behaviour) left half-ingested documents behind when a
    later chunk failed, which then silently polluted every search."""
    rows = [
        KnowledgeChunk(org_id=org_id, source=source, content=content, embedding=embedding)
        for content, embedding in chunks
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


async def delete_source(db: AsyncSession, org_id: uuid.UUID, source: str) -> None:
    """Removes an org's existing chunks for a filename so a re-upload replaces
    the document instead of duplicating it. Always org-scoped."""
    await db.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.org_id == org_id, KnowledgeChunk.source == source)
    )


async def search(
    db: AsyncSession, org_id: uuid.UUID, query_embedding: list[float], top_k: int = 5
) -> list[tuple[KnowledgeChunk, float]]:
    """Returns the top_k chunks for this org ranked by cosine distance to
    `query_embedding` (ascending — smaller distance is more similar), paired
    with their distance score."""
    distance = KnowledgeChunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(KnowledgeChunk, distance.label("distance"))
        .where(KnowledgeChunk.org_id == org_id)
        .order_by(distance)
        .limit(top_k)
    )
    result = await db.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]
