"""Postgres-backed memory models: long-term facts and semantic knowledge chunks."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.db import Base

EMBEDDING_DIM = 1536


class MemoryFact(Base):
    """A durable key/value fact an agent has learned about an org (e.g. business
    hours, a customer preference), scoped by org and agent so agents don't leak
    context across each other or across tenants."""

    __tablename__ = "memory_facts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_memory_facts_org_agent_key", "org_id", "agent_id", "key"),)


class KnowledgeChunk(Base):
    """A chunk of ingested document text plus its embedding, used for semantic
    (RAG-style) search over an org's knowledge base."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
