"""SQLAlchemy models for the PoC SQLite database.

These mirror the backend schema (backend/app/models/receipt.py) but use
SQLite-compatible types so the PoC runs without a Postgres instance.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Integer, String, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    merchant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    billing_period: Mapped[str | None] = mapped_column(String(20), nullable=True)

    category: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="paper")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="VND")

    subtotal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False)

    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    items: Mapped[list[ReceiptItem]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    receipt_id: Mapped[str] = mapped_column(
        String, ForeignKey("receipts.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_raw: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="high")

    toppings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    modifiers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    food_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)

    receipt: Mapped[Receipt] = relationship(back_populates="items")
