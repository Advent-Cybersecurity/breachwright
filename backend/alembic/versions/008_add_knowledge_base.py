"""add knowledge base tables

Revision ID: 008
Revises: 007
Create Date: 2026-03-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fingerprint", sa.String(64), unique=True, nullable=False),
        sa.Column("canonical_title", sa.String(500), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "network", "web", "authentication", "authorization",
                "cryptography", "configuration", "active_directory",
                "cloud", "wireless", "social_engineering", "physical", "other",
                name="findingcategory",
            ),
            nullable=False,
            server_default="other",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("default_severity", sa.String(20), nullable=True),
        sa.Column("default_cvss", sa.Float(), nullable=True),
        sa.Column("cwe_id", sa.String(20), nullable=True),
        sa.Column("mitre_attack_id", sa.String(20), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_client_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_fingerprint", "knowledge_entries", ["fingerprint"], unique=True)
    op.create_index("ix_knowledge_category_severity", "knowledge_entries", ["category", "default_severity"])

    op.create_table(
        "finding_knowledge_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("finding_id", sa.String(36), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_entry_id", sa.String(36), sa.ForeignKey("knowledge_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", sa.String(36), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fkl_finding", "finding_knowledge_links", ["finding_id"])
    op.create_index("ix_fkl_knowledge", "finding_knowledge_links", ["knowledge_entry_id"])
    op.create_index("ix_fkl_engagement", "finding_knowledge_links", ["engagement_id"])
    op.create_index("ix_fkl_knowledge_client", "finding_knowledge_links", ["knowledge_entry_id", "client_name"])


def downgrade() -> None:
    op.drop_table("finding_knowledge_links")
    op.drop_table("knowledge_entries")
    op.execute("DROP TYPE IF EXISTS findingcategory")
