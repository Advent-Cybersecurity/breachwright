"""add report templates

Revision ID: 007
Revises: 006
Create Date: 2026-03-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("logo_path", sa.String(500), nullable=True),
        sa.Column("primary_color", sa.String(7), nullable=True, server_default="#dc2626"),
        sa.Column("secondary_color", sa.String(7), nullable=True, server_default="#1a1a25"),
        sa.Column("header_text", sa.String(500), nullable=True),
        sa.Column("footer_text", sa.String(500), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("report_templates")
