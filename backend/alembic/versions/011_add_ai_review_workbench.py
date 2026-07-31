"""add evidence-grounded AI finding drafts

Revision ID: 011
Revises: 010
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ad_attack_paths", sa.Column("evidence_refs", sa.JSON(), nullable=True))
    op.add_column("findings", sa.Column("evidence_refs", sa.JSON(), nullable=True))
    op.add_column("findings", sa.Column("ai_confidence", sa.Numeric(4, 3), nullable=True))
    op.add_column(
        "findings",
        sa.Column(
            "ai_inference",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "ai_finding_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "engagement_id",
            sa.String(36),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_finding_id",
            sa.String(36),
            sa.ForeignKey("findings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("operation", sa.String(20), nullable=False, server_default="create"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("cvss_score", sa.Numeric(3, 1), nullable=True),
        sa.Column("affected_hosts", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_ai_finding_drafts_engagement_status",
        "ai_finding_drafts",
        ["engagement_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_finding_drafts_engagement_status",
        table_name="ai_finding_drafts",
    )
    op.drop_table("ai_finding_drafts")
    op.drop_column("findings", "ai_inference")
    op.drop_column("findings", "ai_confidence")
    op.drop_column("findings", "evidence_refs")
    op.drop_column("ad_attack_paths", "evidence_refs")
