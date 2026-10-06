"""add privacy review audit fields

Revision ID: d16f8a9b2042
Revises: c05d6e3f7081
Create Date: 2026-10-06 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d16f8a9b2042"
down_revision: Union[str, None] = "c05d6e3f7081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sanitized_exports", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reviewer", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("processing_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sanitized_exports", schema=None) as batch_op:
        batch_op.drop_column("processing_ms")
        batch_op.drop_column("reviewer")
