"""add direct uploads

Revision ID: e27a6b4c9130
Revises: d16f8a9b2042
Create Date: 2026-10-07 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e27a6b4c9130"
down_revision: Union[str, None] = "d16f8a9b2042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_sha256", sa.String(length=64), nullable=True))
    op.create_table(
        "direct_uploads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("expected_size", sa.Integer(), nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=False),
        sa.Column("sampling_profile", sa.String(length=50), nullable=False),
        sa.Column("sample_fps", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("video_id"),
    )
    with op.batch_alter_table("direct_uploads", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_direct_uploads_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("direct_uploads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_direct_uploads_status"))
    op.drop_table("direct_uploads")
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_column("source_sha256")
