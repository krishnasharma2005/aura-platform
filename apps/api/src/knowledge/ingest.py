"""Document ingestion: extract text from PDF/DOCX, chunk it, embed the chunks,
and store them for semantic search."""

import asyncio
import io
import uuid

from docx import Document as DocxDocument
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_gateway.gateway import AIGateway
from src.core.exceptions import ValidationError
from src.knowledge.chunking import chunk_text
from src.memory import semantic
from src.memory.models import KnowledgeChunk

SUPPORTED_EXTENSIONS = {"pdf", "docx"}


def _extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx_text(file_bytes: bytes) -> str:
    document = DocxDocument(io.BytesIO(file_bytes))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def extract_text(filename: str, file_bytes: bytes) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValidationError("We can only read PDF or Word (.docx) documents right now.")
    if extension == "pdf":
        return _extract_pdf_text(file_bytes)
    return _extract_docx_text(file_bytes)


async def ingest_document(
    db: AsyncSession,
    gateway: AIGateway,
    org_id: uuid.UUID,
    filename: str,
    file_bytes: bytes,
) -> list[KnowledgeChunk]:
    """Extracts, chunks, embeds, and stores a document's contents as searchable
    knowledge chunks for the given org."""
    # PDF/DOCX parsing is CPU-bound and synchronous — a 200-page PDF parsed
    # inline would freeze the event loop for every other request in the worker.
    text = await asyncio.to_thread(extract_text, filename, file_bytes)
    chunks = chunk_text(text)
    if not chunks:
        raise ValidationError("That document doesn't seem to have any readable text in it.")

    embeddings = await gateway.embed(chunks)

    # Re-uploading the same filename replaces the document rather than adding a
    # second copy of it to search results.
    await semantic.delete_source(db, org_id, filename)
    return await semantic.add_chunks(
        db, org_id=org_id, source=filename, chunks=list(zip(chunks, embeddings, strict=True))
    )
