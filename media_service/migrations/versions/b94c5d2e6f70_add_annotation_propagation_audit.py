"""add annotation propagation audit

Revision ID: b94c5d2e6f70
Revises: a83b2c1d4e5f
Create Date: 2026-10-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b94c5d2e6f70"
down_revision: Union[str, None] = "a83b2c1d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "annotation_propagations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("model_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_prediction_id", sa.String(length=36), nullable=False),
        sa.Column("source_frame_id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=100), nullable=False),
        sa.Column("start_frame_number", sa.Integer(), nullable=False),
        sa.Column("end_frame_number", sa.Integer(), nullable=False),
        sa.Column("source_geometry", sa.JSON(), nullable=False),
        sa.Column("correction_delta", sa.JSON(), nullable=False),
        sa.Column("generated_count", sa.Integer(), nullable=False),
        sa.Column("reviewer", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_frame_id"], ["frames.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_prediction_id"], ["model_predictions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["annotation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("annotation_propagations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_annotation_propagations_model_run_id"),
            ["model_run_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_annotation_propagations_source_frame_id"),
            ["source_frame_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_annotation_propagations_source_prediction_id"),
            ["source_prediction_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_annotation_propagations_task_id"), ["task_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_annotation_propagations_track_id"), ["track_id"], unique=False
        )

    with op.batch_alter_table("annotations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("propagation_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_annotations_propagation_id",
            "annotation_propagations",
            ["propagation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_annotations_propagation_id"), ["propagation_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("annotations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_annotations_propagation_id"))
        batch_op.drop_constraint("fk_annotations_propagation_id", type_="foreignkey")
        batch_op.drop_column("propagation_id")

    with op.batch_alter_table("annotation_propagations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_annotation_propagations_track_id"))
        batch_op.drop_index(batch_op.f("ix_annotation_propagations_task_id"))
        batch_op.drop_index(batch_op.f("ix_annotation_propagations_source_prediction_id"))
        batch_op.drop_index(batch_op.f("ix_annotation_propagations_source_frame_id"))
        batch_op.drop_index(batch_op.f("ix_annotation_propagations_model_run_id"))
    op.drop_table("annotation_propagations")
