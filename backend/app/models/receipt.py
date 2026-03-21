import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )

    merchant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billing_period: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # "2025-03"

    category: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="paper")

    subtotal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_rate: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    tax_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="VND")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="receipts")
    conversation: Mapped["Conversation | None"] = relationship(
        back_populates="receipts"
    )
    items: Mapped[list["ReceiptItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_raw: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="high")

    toppings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    modifiers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    food_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    receipt: Mapped["Receipt"] = relationship(back_populates="items")
