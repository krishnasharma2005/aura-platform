import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import Base and every model module so autogenerate can see the full schema.
from src.core.config import get_settings
from src.agents.approvals import ToolApproval  # noqa: F401
from src.conversations.models import Contact, Conversation, Message  # noqa: F401
from src.core.db import Base
from src.events.audit import AuditLog  # noqa: F401
from src.identity.models import Membership, Organization, User  # noqa: F401
from src.memory.models import KnowledgeChunk, MemoryFact  # noqa: F401
from src.tools.models import Integration  # noqa: F401
from src.workflows.models import (  # noqa: F401
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStepRun,
)

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
