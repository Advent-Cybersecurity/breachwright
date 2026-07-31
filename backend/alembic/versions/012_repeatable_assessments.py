"""add repeatable assessment workflow

Revision ID: 012
Revises: 011
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("engagements", sa.Column("template_key", sa.String(50), nullable=True))
    op.add_column("findings", sa.Column("retest_due_date", sa.Date(), nullable=True))
    op.create_table(
        "finding_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("finding_id", sa.String(36), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", sa.String(36), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_finding_history_finding_created", "finding_history", ["finding_id", "created_at"])
    op.create_table(
        "scan_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("engagement_id", sa.String(36), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("source_scan_ids", sa.JSON(), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False, server_default="structured-v1"),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scan_snapshots_engagement_created", "scan_snapshots", ["engagement_id", "created_at"])
    op.create_table(
        "scan_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("scan_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("tool", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("host", sa.String(500), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("evidence_ref", sa.JSON(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "fingerprint", name="uq_scan_observation_snapshot_fingerprint"),
    )
    op.create_index("ix_scan_observations_fingerprint", "scan_observations", ["fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_scan_observations_fingerprint", table_name="scan_observations")
    op.drop_table("scan_observations")
    op.drop_index("ix_scan_snapshots_engagement_created", table_name="scan_snapshots")
    op.drop_table("scan_snapshots")
    op.drop_index("ix_finding_history_finding_created", table_name="finding_history")
    op.drop_table("finding_history")
    op.drop_column("findings", "retest_due_date")
    op.drop_column("engagements", "template_key")
