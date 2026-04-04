"""add weekly usage reports

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add weekly report settings to user_settings
    op.add_column(
        "user_settings",
        sa.Column("weekly_report_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "user_settings",
        sa.Column("weekly_report_custom_format", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_settings",
        sa.Column("weekly_report_custom_analysis", sa.Text(), nullable=True),
    )

    # Create weekly_usage_reports table
    op.create_table(
        "weekly_usage_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("report_content", sa.Text(), nullable=True),
    )
    op.create_index("ix_weekly_usage_reports_user_id", "weekly_usage_reports", ["user_id"])
    op.create_index(
        "ix_weekly_usage_reports_user_week",
        "weekly_usage_reports",
        ["user_id", "week_start"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_weekly_usage_reports_user_week", table_name="weekly_usage_reports")
    op.drop_index("ix_weekly_usage_reports_user_id", table_name="weekly_usage_reports")
    op.drop_table("weekly_usage_reports")
    op.drop_column("user_settings", "weekly_report_custom_analysis")
    op.drop_column("user_settings", "weekly_report_custom_format")
    op.drop_column("user_settings", "weekly_report_enabled")