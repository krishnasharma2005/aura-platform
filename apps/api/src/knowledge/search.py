"""Given a query string, embed it and semantically search an org's knowledge
base, returning top-k chunks with source metadata."""

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_gateway.gateway import AIGateway
from src.memory import semantic


class KnowledgeResult(BaseModel):
    content: str
    source: str
    distance: float


async def search_knowledge(
    db: AsyncSession, gateway: AIGateway, org_id: uuid.UUID, query: str, top_k: int = 5
) -> list[KnowledgeResult]:
    [query_embedding] = await gateway.embed([query])
    matches = await semantic.search(db, org_id=org_id, query_embedding=query_embedding, top_k=top_k)
    return [KnowledgeResult(content=chunk.content, source=chunk.source, distance=distance) for chunk, distance in matches]
