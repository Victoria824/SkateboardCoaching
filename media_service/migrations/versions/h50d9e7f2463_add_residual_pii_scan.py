"""add residual PII scan fields

Revision ID: h50d9e7f2463
Revises: g49c8d6e1352
Create Date: 2026-10-07 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h50d9e7f2463"
down_revision: Union[str, None] = "g49c8d6e1352"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sanitized_exports", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("residual_scan_status", sa.String(length=30), nullable=False, server_default="NOT_RUN")
        )
        batch_op.add_column(
            sa.Column("residual_findings", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("residual_model_version", sa.String(length=255), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("sanitized_exports", schema=None) as batch_op:
        batch_op.drop_column("residual_model_version")
        batch_op.drop_column("residual_findings")
        batch_op.drop_column("residual_scan_status")
