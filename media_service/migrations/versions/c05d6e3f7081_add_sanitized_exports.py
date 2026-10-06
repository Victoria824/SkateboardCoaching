"""add sanitized exports

Revision ID: c05d6e3f7081
Revises: b94c5d2e6f70
Create Date: 2026-10-06 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c05d6e3f7081"
down_revision: Union[str, None] = "b94c5d2e6f70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sanitized_exports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("source_annotation_count", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.Column("output_sha256", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["annotation_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sanitized_exports", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sanitized_exports_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_sanitized_exports_task_id"), ["task_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sanitized_exports_video_id"), ["video_id"], unique=False)
    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sanitized_export_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_processing_jobs_sanitized_export_id",
            "sanitized_exports",
            ["sanitized_export_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            batch_op.f("ix_processing_jobs_sanitized_export_id"),
            ["sanitized_export_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_processing_jobs_sanitized_export_id"))
        batch_op.drop_constraint("fk_processing_jobs_sanitized_export_id", type_="foreignkey")
        batch_op.drop_column("sanitized_export_id")
    with op.batch_alter_table("sanitized_exports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sanitized_exports_video_id"))
        batch_op.drop_index(batch_op.f("ix_sanitized_exports_task_id"))
        batch_op.drop_index(batch_op.f("ix_sanitized_exports_status"))
    op.drop_table("sanitized_exports")
