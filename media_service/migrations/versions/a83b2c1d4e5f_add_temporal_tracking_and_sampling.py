"""add temporal tracking and sampling

Revision ID: a83b2c1d4e5f
Revises: 6e37c373ffe1
Create Date: 2026-10-05 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a83b2c1d4e5f"
down_revision: Union[str, None] = "6e37c373ffe1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "sampling_profile",
                sa.String(length=50),
                server_default="overview",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("sample_fps", sa.Float(), server_default="1.0", nullable=False)
        )
        batch_op.create_index(
            batch_op.f("ix_videos_sampling_profile"), ["sampling_profile"], unique=False
        )

    with op.batch_alter_table("model_predictions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("track_id", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column("associated_prediction_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(sa.Column("association_score", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "association_ambiguous",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.create_foreign_key(
            "fk_model_predictions_associated_prediction_id",
            "model_predictions",
            ["associated_prediction_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_model_predictions_associated_prediction_id"),
            ["associated_prediction_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_model_predictions_track_id"), ["track_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("model_predictions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_model_predictions_track_id"))
        batch_op.drop_index(batch_op.f("ix_model_predictions_associated_prediction_id"))
        batch_op.drop_constraint(
            "fk_model_predictions_associated_prediction_id", type_="foreignkey"
        )
        batch_op.drop_column("association_ambiguous")
        batch_op.drop_column("association_score")
        batch_op.drop_column("associated_prediction_id")
        batch_op.drop_column("track_id")

    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_videos_sampling_profile"))
        batch_op.drop_column("sample_fps")
        batch_op.drop_column("sampling_profile")
