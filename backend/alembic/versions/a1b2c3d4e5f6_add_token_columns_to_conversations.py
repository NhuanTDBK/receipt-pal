"""add token columns to conversations

Revision ID: a1b2c3d4e5f6
Revises: ddcdb3baa948
Create Date: 2026-03-13 08:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "ddcdb3baa948"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "conversations",
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "conversations",
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("conversations", "total_tokens")
    op.drop_column("conversations", "output_tokens")
    op.drop_column("conversations", "input_tokens")
