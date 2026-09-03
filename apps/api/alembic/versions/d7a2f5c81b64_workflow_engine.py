"""workflow engine: stored definitions, runs, and per-step results

Revision ID: d7a2f5c81b64
Revises: c3e91b4d75a2
Create Date: 2026-08-15

The Workflow Engine. Three tables, one design decision:

**Definitions are rows, not code.** A workflow is a trigger plus an ordered
list of steps stored as JSON on `workflow_definitions`, owned by one
organization. Two clinics can run the same template with different recall
intervals; one can have it on while the other has it off; and the Phase 2
visual builder writes rows rather than pull requests.

`workflow_runs` and `workflow_step_runs` are the history the dashboard reads.
Per-step rows exist so a failure is answerable — "the reminder didn't go out
because WhatsApp isn't connected", not "the workflow failed".

`locked_at` / `locked_by` on both the definition and the run are the DB-level
claim that makes the scheduler safe on more than one API instance without a
broker. Claiming is a conditional UPDATE that advances `next_run_at` in the
same statement, so a racing instance matches zero rows. See
`src/workflows/runner.py`.

No data migration is needed: templates are installed per organization on
first read of `GET /api/v1/workflows` (and by the demo seed), all disabled
until an owner turns one on.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7a2f5c81b64'
down_revision: Union[str, Sequence[str], None] = 'c3e91b4d75a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'workflow_definitions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column(
            'trigger_type',
            sa.Enum('schedule', 'event', name='workflow_trigger_type'),
            nullable=False,
        ),
        sa.Column('trigger_config', sa.JSON(), nullable=False),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('run_count', sa.Integer(), nullable=False),
        sa.Column('success_count', sa.Integer(), nullable=False),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('locked_by', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'slug', name='uq_workflow_definitions_org_slug'),
    )
    op.create_index(
        op.f('ix_workflow_definitions_org_id'), 'workflow_definitions', ['org_id'], unique=False
    )
    # The scheduler's only query: "what is due, for anyone, right now?"
    op.create_index(
        'ix_workflow_definitions_enabled_next_run',
        'workflow_definitions',
        ['enabled', 'next_run_at'],
        unique=False,
    )

    op.create_table(
        'workflow_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('workflow_id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('running', 'success', 'failed', name='workflow_run_status'),
            nullable=False,
        ),
        sa.Column('trigger_source', sa.String(length=50), nullable=False),
        sa.Column('context', sa.JSON(), nullable=False),
        sa.Column('next_step_index', sa.Integer(), nullable=False),
        sa.Column('resume_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.String(length=500), nullable=True),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('locked_by', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow_definitions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflow_runs_org_id'), 'workflow_runs', ['org_id'], unique=False)
    op.create_index(
        op.f('ix_workflow_runs_workflow_id'), 'workflow_runs', ['workflow_id'], unique=False
    )
    op.create_index(
        'ix_workflow_runs_org_started', 'workflow_runs', ['org_id', 'started_at'], unique=False
    )
    # Feeds "which parked runs are ready to move on?" on every tick.
    op.create_index(
        'ix_workflow_runs_status_resume', 'workflow_runs', ['status', 'resume_at'], unique=False
    )

    op.create_table(
        'workflow_step_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('step_id', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('step_type', sa.String(length=50), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'success',
                'failed',
                'skipped',
                'awaiting_approval',
                'waiting',
                name='workflow_step_status',
            ),
            nullable=False,
        ),
        sa.Column('detail', sa.String(length=1000), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_workflow_step_runs_run_id'), 'workflow_step_runs', ['run_id'], unique=False
    )
    op.create_index(
        'ix_workflow_step_runs_run_position',
        'workflow_step_runs',
        ['run_id', 'position'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_workflow_step_runs_run_position', table_name='workflow_step_runs')
    op.drop_index(op.f('ix_workflow_step_runs_run_id'), table_name='workflow_step_runs')
    op.drop_table('workflow_step_runs')
    sa.Enum(name='workflow_step_status').drop(op.get_bind(), checkfirst=True)

    op.drop_index('ix_workflow_runs_status_resume', table_name='workflow_runs')
    op.drop_index('ix_workflow_runs_org_started', table_name='workflow_runs')
    op.drop_index(op.f('ix_workflow_runs_workflow_id'), table_name='workflow_runs')
    op.drop_index(op.f('ix_workflow_runs_org_id'), table_name='workflow_runs')
    op.drop_table('workflow_runs')
    sa.Enum(name='workflow_run_status').drop(op.get_bind(), checkfirst=True)

    op.drop_index('ix_workflow_definitions_enabled_next_run', table_name='workflow_definitions')
    op.drop_index(op.f('ix_workflow_definitions_org_id'), table_name='workflow_definitions')
    op.drop_table('workflow_definitions')
    sa.Enum(name='workflow_trigger_type').drop(op.get_bind(), checkfirst=True)
