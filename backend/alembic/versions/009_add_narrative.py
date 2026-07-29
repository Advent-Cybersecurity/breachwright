"""add narrative to attack paths

Revision ID: 009
Revises: 008
Create Date: 2026-03-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("attack_paths") as batch_op:
        batch_op.add_column(sa.Column("narrative", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("mitre_techniques", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attack_paths") as batch_op:
        batch_op.drop_column("narrative")
        batch_op.drop_column("mitre_techniques")
