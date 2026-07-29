"""add methodology checklists

Revision ID: 006
Revises: 005
Create Date: 2026-03-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "methodology_checklists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("engagement_id", sa.String(36), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("methodology", sa.String(100), nullable=False),
        sa.Column("category", sa.String(200), nullable=False),
        sa.Column("item", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tools", sa.String(500), nullable=True),
        sa.Column("techniques", sa.String(500), nullable=True),
        sa.Column("reference_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_checklist_engagement", "methodology_checklists", ["engagement_id"])
    op.create_index("ix_checklist_methodology", "methodology_checklists", ["methodology"])


def downgrade() -> None:
    op.drop_table("methodology_checklists")
