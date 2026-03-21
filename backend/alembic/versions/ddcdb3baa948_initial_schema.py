"""initial schema

Revision ID: ddcdb3baa948
Revises:
Create Date: 2026-03-12 15:36:29.324446

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "ddcdb3baa948"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("image_file_ids", JSONB(), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("tool_args", JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_conversation_messages_conversation_id",
        "conversation_messages",
        ["conversation_id"],
    )

    op.create_table(
        "receipts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("merchant_name", sa.String(255), nullable=False),
        sa.Column("merchant_address", sa.String(500), nullable=True),
        sa.Column("receipt_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billing_period", sa.String(20), nullable=True),
        sa.Column("category", sa.String(50), nullable=False, server_default="other"),
        sa.Column("source", sa.String(50), nullable=False, server_default="paper"),
        sa.Column("subtotal", sa.Integer(), nullable=True),
        sa.Column("discount", sa.Integer(), nullable=True),
        sa.Column("tax_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("tax_amount", sa.Integer(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="VND"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_receipts_user_id", "receipts", ["user_id"])

    op.create_table(
        "receipt_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "receipt_id",
            UUID(as_uuid=True),
            sa.ForeignKey("receipts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("name_raw", sa.String(500), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="high"),
        sa.Column("toppings", JSONB(), nullable=True),
        sa.Column("modifiers", JSONB(), nullable=True),
        sa.Column("food_tags", JSONB(), nullable=True),
    )
    op.create_index("ix_receipt_items_receipt_id", "receipt_items", ["receipt_id"])


def downgrade() -> None:
    op.drop_table("receipt_items")
    op.drop_table("receipts")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
    op.drop_table("users")
