"""Workflow engine data model.

Three tables, and one deliberate architectural choice behind all of them:
**workflow definitions live in the database, not in code** (architecture doc,
"workflows are data"). A definition is a trigger plus an ordered list of steps
stored as JSON, owned by one organization. That means an owner can have a
template enabled while another org has it off, the intervals can differ per
customer, and Phase 2's visual builder writes rows instead of pull requests.

  workflow_definitions  — the recipe: trigger + steps + enabled + counters
  workflow_runs         — one execution attempt of a definition
  workflow_step_runs    — what each step did, so a failure is debuggable

Everything is org-scoped by construction. A run is only ever loaded by
(org_id, id) through `src/workflows/service.py`, so a workflow id from one
tenant never resolves in another.

Concurrency: `locked_at` / `locked_by` on both the definition and the run are
the DB-level claim that makes it safe to run more than one API instance. See
`src/workflows/service.py::claim_due_definitions` for the compare-and-swap.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.db import Base


class TriggerType(str, enum.Enum):
    """How a workflow starts.

    `schedule` — the background runner fires it when `next_run_at` comes due.
    `event`    — it subscribes to a name on the in-process event bus
                 (`src/events/bus.py`), e.g. a customer message arriving.
    """

    schedule = "schedule"
    event = "event"


class RunStatus(str, enum.Enum):
    """`running` covers a run that is mid-flight *and* a run parked on a wait
    step — from the owner's point of view both are "still going"."""

    running = "running"
    success = "success"
    failed = "failed"


class StepStatus(str, enum.Enum):
    success = "success"
    failed = "failed"
    skipped = "skipped"
    # A consequential tool the workflow wanted to use. It was NOT executed; a
    # row is sitting in `tool_approvals` waiting for a human. A workflow is
    # never a way around the approval gate.
    awaiting_approval = "awaiting_approval"
    waiting = "waiting"


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    __table_args__ = (
        # A template is seeded once per organization.
        UniqueConstraint("org_id", "slug", name="uq_workflow_definitions_org_slug"),
        # The scheduler's only query: "what is due, for anyone, right now?"
        Index("ix_workflow_definitions_enabled_next_run", "enabled", "next_run_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType, name="workflow_trigger_type"), nullable=False
    )
    # schedule: {"interval_minutes": 1440, ...template-specific settings}
    # event:    {"event": "conversation.message_received", "channels": [...]}
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # The ordered step list. See src/workflows/steps.py for the shape.
    steps: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    locked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class WorkflowRun(Base):
    """One execution. A run that hits a `wait` step is *suspended*, not held in
    memory: `next_step_index` and `resume_at` are persisted and the runner picks
    it up later. That is what lets "remind, then check back tomorrow" survive a
    deploy."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_org_started", "org_id", "started_at"),
        Index("ix_workflow_runs_status_resume", "status", "resume_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="workflow_run_status"), nullable=False, default=RunStatus.running
    )
    # "schedule" | "event" | "manual" — how this particular run got started.
    trigger_source: Mapped[str] = mapped_column(String(50), nullable=False, default="schedule")
    # Accumulated state: the trigger payload plus each step's output, which is
    # what the {{...}} placeholders in the step definitions read from.
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    next_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resume_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Plain language, shown to the owner. Never a stack trace.
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    locked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class WorkflowStepRun(Base):
    """The per-step record. This is the difference between "the workflow
    failed" and "the workflow failed because WhatsApp isn't connected yet"."""

    __tablename__ = "workflow_step_runs"
    __table_args__ = (Index("ix_workflow_step_runs_run_position", "run_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="workflow_step_status"), nullable=False
    )
    detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
