"""Workflow routes: what automations this business has, whether they're on,
and what they've actually done.

The run history is the point. "Agents that work autonomously" is only a
credible claim if the owner can open a screen and see the machinery — which
reminder went out, which one is waiting on their approval, which step failed
and why. Everything here is org-scoped through `get_active_organization`, so a
workflow id from another business is simply not found.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.identity.deps import get_active_organization, require_org_role
from src.identity.models import MembershipRole, Organization
from src.workflows import service as workflow_service
from src.workflows.models import WorkflowDefinition, WorkflowRun

router = APIRouter(prefix="/workflows", tags=["workflows"])

# Turning an automation on means it will start messaging customers, so it is
# an owner/admin decision — the same bar as approving an action.
_operator = require_org_role(MembershipRole.owner, MembershipRole.admin)


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    trigger: str
    enabled: bool
    last_run_at: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0


class WorkflowStepRunResponse(BaseModel):
    name: str
    status: str
    detail: Optional[str] = None


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    steps: list[WorkflowStepRunResponse] = []


def _describe_trigger(definition: WorkflowDefinition) -> str:
    """Plain language, not a cron string. An owner reads "every day", not
    "*/1440"."""
    config = definition.trigger_config or {}
    if definition.trigger_type.value == "event":
        return "When a new enquiry comes in"
    minutes = int(config.get("interval_minutes") or 0)
    if minutes and minutes % (60 * 24 * 7) == 0:
        weeks = minutes // (60 * 24 * 7)
        return "Every week" if weeks == 1 else f"Every {weeks} weeks"
    if minutes and minutes % (60 * 24) == 0:
        days = minutes // (60 * 24)
        return "Every day" if days == 1 else f"Every {days} days"
    if minutes and minutes % 60 == 0:
        hours = minutes // 60
        return "Every hour" if hours == 1 else f"Every {hours} hours"
    return f"Every {minutes} minutes" if minutes else "On a schedule"


def _to_response(definition: WorkflowDefinition) -> WorkflowResponse:
    return WorkflowResponse(
        id=str(definition.id),
        name=definition.name,
        description=definition.description or "",
        trigger=_describe_trigger(definition),
        enabled=bool(definition.enabled),
        last_run_at=definition.last_run_at,
        run_count=definition.run_count or 0,
        success_count=definition.success_count or 0,
    )


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowResponse]:
    definitions = await workflow_service.list_definitions(db, organization.id)
    if not definitions:
        # An org created before workflows existed (or one that has never
        # opened the screen) gets the templates installed, switched off, on
        # first read. Saves a backfill migration and an empty-state dead end.
        definitions = await workflow_service.seed_templates(db, organization.id)
    return [_to_response(definition) for definition in definitions]


@router.post("/{workflow_id}/enable", response_model=WorkflowResponse)
async def enable_workflow(
    workflow_id: uuid.UUID,
    organization: Organization = Depends(_operator),
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    definition = await workflow_service.set_enabled(db, organization.id, workflow_id, True)
    return _to_response(definition)


@router.post("/{workflow_id}/disable", response_model=WorkflowResponse)
async def disable_workflow(
    workflow_id: uuid.UUID,
    organization: Organization = Depends(_operator),
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    definition = await workflow_service.set_enabled(db, organization.id, workflow_id, False)
    return _to_response(definition)


@router.get("/{workflow_id}/runs", response_model=list[WorkflowRunResponse])
async def list_workflow_runs(
    workflow_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    organization: Organization = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowRunResponse]:
    runs: list[WorkflowRun] = await workflow_service.list_runs(
        db, organization.id, workflow_id, limit=limit
    )
    steps_by_run = await workflow_service.get_step_runs(db, [run.id for run in runs])
    return [
        WorkflowRunResponse(
            id=str(run.id),
            workflow_id=str(run.workflow_id),
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            steps=[
                WorkflowStepRunResponse(name=step.name, status=step.status.value, detail=step.detail)
                for step in steps_by_run.get(run.id, [])
            ],
        )
        for run in runs
    ]
