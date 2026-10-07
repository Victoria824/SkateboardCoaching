"""add job outbox

Revision ID: g49c8d6e1352
Revises: f38b7c5d0241
Create Date: 2026-10-07 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g49c8d6e1352"
down_revision: Union[str, None] = "f38b7c5d0241"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("job_outbox", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_job_outbox_job_id"), ["job_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_job_outbox_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("job_outbox", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_job_outbox_status"))
        batch_op.drop_index(batch_op.f("ix_job_outbox_job_id"))
    op.drop_table("job_outbox")
