"""Knowledge routes: upload a document to the org's knowledge base, list what's
been uploaded, and search it."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_gateway.gateway import AIGateway
from src.core.config import get_settings
from src.core.db import get_db
from src.core.exceptions import ValidationError
from src.identity.deps import get_active_organization
from src.identity.models import Organization
from src.knowledge.ingest import ingest_document
from src.knowledge.search import KnowledgeResult, search_knowledge
from src.memory.models import KnowledgeChunk

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class IngestResponse(BaseModel):
    chunks_stored: int


class KnowledgeDocument(BaseModel):
    id: str
    filename: str
    status: str
    uploaded_at: datetime


def get_gateway() -> AIGateway:
    return AIGateway()


async def _read_capped(file: UploadFile) -> bytes:
    """Reads the upload in chunks and stops as soon as it exceeds the limit.
    Reading the whole body first (the previous behaviour) meant any authenticated
    member could OOM the API with a single large POST."""
    limit = get_settings().MAX_UPLOAD_BYTES
    buffer = bytearray()
    while chunk := await file.read(1024 * 1024):
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise ValidationError(
                f"That file is too large. Please upload a document under {limit // (1024 * 1024)} MB."
            )
    return bytes(buffer)


@router.post("/upload", response_model=IngestResponse)
async def upload_document(
    file: UploadFile,
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
    gateway: AIGateway = Depends(get_gateway),
) -> IngestResponse:
    file_bytes = await _read_capped(file)
    chunks = await ingest_document(db, gateway, organization.id, file.filename or "document", file_bytes)
    return IngestResponse(chunks_stored=len(chunks))


@router.get("", response_model=list[KnowledgeDocument])
async def list_documents(
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeDocument]:
    """One row per uploaded document (grouped by source filename), not per
    chunk — a document that ingested into 40 chunks should still show as one
    row in the UI."""
    stmt = (
        select(
            KnowledgeChunk.source,
            # Cast to text: Postgres has no min(uuid) aggregate, so grouping on
            # the raw uuid column errors out on the real database (sqlite, which
            # stores Uuid as CHAR(32), happily hides this in tests).
            func.min(cast(KnowledgeChunk.id, String)).label("id"),
            func.max(KnowledgeChunk.created_at).label("uploaded_at"),
        )
        .where(KnowledgeChunk.org_id == organization.id)
        .group_by(KnowledgeChunk.source)
        .order_by(func.max(KnowledgeChunk.created_at).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        KnowledgeDocument(id=str(row.id), filename=row.source, status="ready", uploaded_at=row.uploaded_at)
        for row in rows
    ]


@router.get("/search", response_model=list[KnowledgeResult])
async def search(
    q: str = Query(..., alias="q"),
    top_k: int = 5,
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
    gateway: AIGateway = Depends(get_gateway),
) -> list[KnowledgeResult]:
    return await search_knowledge(db, gateway, organization.id, q, top_k=top_k)
