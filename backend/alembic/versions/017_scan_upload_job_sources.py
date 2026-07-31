"""link Tool Runner jobs to scan uploads

Revision ID: 017
Revises: 016
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("scan_uploads") as batch_op:
        batch_op.add_column(sa.Column("source_job_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_scan_uploads_source_job_id",
            "jobs",
            ["source_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "uq_scan_uploads_source_job_id",
            ["source_job_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("scan_uploads") as batch_op:
        batch_op.drop_index("uq_scan_uploads_source_job_id")
        batch_op.drop_constraint("fk_scan_uploads_source_job_id", type_="foreignkey")
        batch_op.drop_column("source_job_id")
