"""add AD analysis tables

Revision ID: 004
Revises: 003
Create Date: 2026-03-04
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ad_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("engagement_id", sa.String(36), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("object_count", sa.Integer(), default=0),
        sa.Column("relationship_count", sa.Integer(), default=0),
        sa.Column("imported_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "ad_objects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("ad_imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_id", sa.String(500), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("object_type", sa.String(50), nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=True),
        sa.Column("properties", sa.JSON(), nullable=True),
    )
    op.create_index("ix_ad_objects_import", "ad_objects", ["import_id"])
    op.create_index("ix_ad_objects_type", "ad_objects", ["object_type"])
    op.create_index("ix_ad_objects_objid", "ad_objects", ["object_id"])

    op.create_table(
        "ad_relationships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("ad_imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(500), nullable=False),
        sa.Column("target_id", sa.String(500), nullable=False),
        sa.Column("relationship_type", sa.String(100), nullable=False),
        sa.Column("is_inherited", sa.Boolean(), default=False),
    )
    op.create_index("ix_ad_rel_import", "ad_relationships", ["import_id"])
    op.create_index("ix_ad_rel_source", "ad_relationships", ["source_id"])
    op.create_index("ix_ad_rel_target", "ad_relationships", ["target_id"])

    op.create_table(
        "ad_attack_paths",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("ad_imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(50), nullable=True),
        sa.Column("path_nodes", sa.JSON(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ad_attack_paths")
    op.drop_table("ad_relationships")
    op.drop_table("ad_objects")
    op.drop_table("ad_imports")
