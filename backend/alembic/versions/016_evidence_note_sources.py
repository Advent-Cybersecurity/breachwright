"""track evidence note source records

Revision ID: 016
Revises: 015
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("evidence_notes") as batch_op:
        batch_op.add_column(
            sa.Column("source_type", sa.String(50), nullable=False, server_default="manual")
        )
        batch_op.add_column(sa.Column("source_id", sa.String(36), nullable=True))
        batch_op.create_index(
            "ix_evidence_notes_source",
            ["engagement_id", "source_type", "source_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("evidence_notes") as batch_op:
        batch_op.drop_index("ix_evidence_notes_source")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source_type")
