"""Test fixtures.

Test DB note: the full test suite runs against a throwaway SQLite database
(sqlite+aiosqlite) instead of Postgres, so `pytest` needs no docker-compose
services running. This covers every model except memory/semantic.py, which
relies on the Postgres-only pgvector `<=>` cosine-distance operator — that
module is not exercised by this suite (see its own docstring).

Test Redis note: short-term memory is backed by a fakeredis in-process stand-in
instead of a real Redis server, wired in via the `fake_redis` autouse fixture
below, so no Redis service is required either.

Both env vars are set *before* importing src.core.config/db so the app's
module-level engine and session factory point at the test database from the
start (this also makes src/events/audit.py's direct use of
`async_session_factory` write to the same test DB, without needing a
dependency-override for code that runs outside a request).
"""

import os
import uuid
from collections.abc import AsyncGenerator

_TEST_DB_PATH = os.path.join(os.path.dirname(__file__), ".aura_test.db")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TEST_DB_PATH}")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENV", "test")
# The workflow runner is an asyncio loop in the app lifespan (see
# src/workflows/runner.py). Tests drive `runner.tick()` explicitly instead, so
# a background loop doesn't race the schema being dropped between tests.
os.environ.setdefault("WORKFLOWS_RUNNER_ENABLED", "false")
os.environ.setdefault("WORKFLOW_RETRY_BACKOFF_SECONDS", "0")
# Blank these out as real *environment variables* (not just unset) so they
# take precedence over whatever a developer's local .env has configured for
# manual testing (see AI_PROVIDER in core/config.py) — pydantic-settings reads
# the .env file directly, so without this a real API key in .env would make
# the suite place real, rate-limited/paid calls instead of the mocked
# FakeGateway path every test actually exercises.
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("AI_PROVIDER", "openai")

import fakeredis
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.approvals import ToolApproval  # noqa: F401  (registers the table on Base.metadata)
from src.agents.business_context import BusinessContext  # noqa: F401  (same)
from src.agents.entitlements import OrgPackEntitlement  # noqa: F401  (same)
from src.conversations.models import Contact, Conversation, Message  # noqa: F401  (same)
from src.core.db import Base, engine, async_session_factory
from src.core.security import create_access_token
from src.identity.models import Membership, MembershipRole, Organization, User
from src.identity.public_id import generate_public_id
from src.memory import short_term as short_term_module
from src.workflows.models import (  # noqa: F401  (registers the workflow tables on Base.metadata)
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStepRun,
)


@pytest_asyncio.fixture(autouse=True)
async def _reset_schema():
    """Recreates the schema fresh for every test so tests are isolated."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture(autouse=True)
def _fake_redis(monkeypatch):
    fake_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(short_term_module, "_redis", fake_client)
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def app():
    from src.main import create_app

    yield create_app()


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def user_and_org(db_session: AsyncSession):
    """Creates a user + org + owner membership directly in the DB, and returns
    (user, org, bearer_headers)."""
    user = User(email="owner@example.com", hashed_password="x", name="Owner")
    db_session.add(user)
    await db_session.flush()

    org = Organization(
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
        public_id=generate_public_id(),
    )
    db_session.add(org)
    await db_session.flush()

    membership = Membership(user_id=user.id, organization_id=org.id, role=MembershipRole.owner, accepted=True)
    db_session.add(membership)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-Id": str(org.id)}
    return user, org, headers
