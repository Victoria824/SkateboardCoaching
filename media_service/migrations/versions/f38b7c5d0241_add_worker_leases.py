"""add worker leases

Revision ID: f38b7c5d0241
Revises: e27a6b4c9130
Create Date: 2026-10-07 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f38b7c5d0241"
down_revision: Union[str, None] = "e27a6b4c9130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("worker_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f("ix_processing_jobs_worker_id"), ["worker_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_processing_jobs_lease_expires_at"),
            ["lease_expires_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_processing_jobs_lease_expires_at"))
        batch_op.drop_index(batch_op.f("ix_processing_jobs_worker_id"))
        batch_op.drop_column("heartbeat_at")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("worker_id")
