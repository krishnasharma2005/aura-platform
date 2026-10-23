"""The workflow migration has to match the ORM, or production and the test
suite disagree about the schema and nobody finds out until a deploy.

The rest of the migration history can't be replayed here (it creates the
Postgres-only pgvector extension), so this applies just the workflow revision
to a scratch SQLite database and diffs the result against `Base.metadata`.
"""

import os
import pathlib
import tempfile

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from src.core.db import Base
from src.workflows import models as workflow_models  # noqa: F401  (registers the tables)

WORKFLOW_TABLES = {"workflow_definitions", "workflow_runs", "workflow_step_runs"}
REVISION = "d7a2f5c81b64_workflow_engine.py"


def _load_revision():
    import importlib.util

    path = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions" / REVISION
    spec = importlib.util.spec_from_file_location("workflow_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_workflow_migration_matches_the_orm_models():
    revision = _load_revision()

    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{os.path.join(directory, 'schema.db')}"
        engine = create_engine(url)

        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                revision.upgrade()

        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    # Only the three tables this revision owns; everything else
                    # in Base.metadata lives in earlier revisions.
                    "include_name": lambda name, type_, parent: (
                        type_ != "table" or name in WORKFLOW_TABLES
                    )
                },
            )
            differences = [
                difference
                for difference in compare_metadata(context, Base.metadata)
                if any(table in repr(difference) for table in WORKFLOW_TABLES)
            ]

        engine.dispose()

    assert differences == [], f"migration and ORM models disagree: {differences}"


def _concerns(difference, tables: set[str]) -> bool:
    """Whether an Alembic diff entry is about one of `tables`. Matching on the
    printed form isn't safe: an unrelated table that merely has a foreign key to
    `users` would match."""
    for entry in difference if isinstance(difference, list) else [difference]:
        kind = entry[0]
        if kind in ("add_table", "remove_table"):
            name = entry[1].name
        elif kind in ("add_column", "remove_column"):
            name = entry[2]
        elif kind in ("add_index", "remove_index", "add_fk", "remove_fk", "add_constraint", "remove_constraint"):
            owner = entry[1]
            name = getattr(getattr(owner, "table", None), "name", None) or getattr(owner, "table_name", None)
        else:
            name = entry[2] if len(entry) > 2 and isinstance(entry[2], str) else None
        if name in tables:
            return True
    return False


def test_the_password_reset_migration_matches_the_orm_models():
    """Same check for the password-reset revision: it adds a table and one column
    on `users`. Start from `users` as it was before (no password_changed_at),
    apply the revision, and diff the two tables it touches against the models."""
    import importlib.util

    from sqlalchemy import text

    from src.identity import models as identity_models  # noqa: F401  (registers the tables)

    path = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions" / "f2b6c0a9d413_password_reset.py"
    spec = importlib.util.spec_from_file_location("password_reset_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    touched = {"users", "password_reset_tokens"}

    with tempfile.TemporaryDirectory() as directory:
        engine = create_engine(f"sqlite:///{os.path.join(directory, 'schema.db')}")
        with engine.begin() as connection:
            Base.metadata.tables["users"].create(connection)
            connection.execute(text("ALTER TABLE users DROP COLUMN password_changed_at"))
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                revision.upgrade()

        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"include_name": lambda name, type_, parent: type_ != "table" or name in touched},
            )
            differences = [
                difference
                for difference in compare_metadata(context, Base.metadata)
                if _concerns(difference, touched)
            ]
        engine.dispose()

    assert differences == [], f"migration and ORM models disagree: {differences}"
