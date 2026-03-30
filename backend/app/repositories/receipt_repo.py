import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.receipt import Receipt, ReceiptItem


async def save_receipt(
    session: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    data: dict[str, Any],
) -> Receipt:
    """Persist a confirmed receipt (with items) to the database."""
    merchant = data.get("merchant", {})
    items_data = data.get("items", [])

    receipt = Receipt(
        id=uuid.uuid4(),
        user_id=user_id,
        conversation_id=conversation_id,
        merchant_name=merchant.get("name", "Unknown"),
        merchant_address=merchant.get("address"),
        receipt_datetime=_parse_datetime(data.get("datetime")),
        billing_period=data.get("billing_period"),
        category=data.get("category", "other"),
        source=data.get("source", "paper"),
        subtotal=data.get("subtotal"),
        discount=data.get("discount"),
        tax_rate=data.get("tax_rate"),
        tax_amount=data.get("tax_amount"),
        total=data.get("total", 0),
        currency=data.get("currency", "VND"),
        notes=data.get("notes"),
    )
    session.add(receipt)
    await session.flush()

    for item_data in items_data:
        item = ReceiptItem(
            id=uuid.uuid4(),
            receipt_id=receipt.id,
            name=item_data.get("name", ""),
            name_raw=item_data.get("name_raw"),
            quantity=item_data.get("quantity", 1),
            unit_price=item_data.get("unit_price"),
            amount=item_data.get("amount", 0),
            confidence=item_data.get("confidence", "high"),
            toppings=item_data.get("toppings"),
            modifiers=item_data.get("modifiers"),
            food_tags=item_data.get("food_tags"),
        )
        session.add(item)

    await session.commit()
    await session.refresh(receipt)
    return receipt


async def list_receipts(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 10
) -> list[Receipt]:
    """List the most recent receipts for a user, including items."""
    result = await session.execute(
        select(Receipt)
        .where(Receipt.user_id == user_id)
        .options(selectinload(Receipt.items))
        .order_by(Receipt.receipt_datetime.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_spending_stats(
    session: AsyncSession, user_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Return total spending grouped by category for a user."""
    result = await session.execute(
        select(Receipt.category, func.sum(Receipt.total).label("total"))
        .where(Receipt.user_id == user_id)
        .group_by(Receipt.category)
        .order_by(func.sum(Receipt.total).desc())
    )
    return [{"category": row.category, "total": row.total} for row in result.all()]


def _parse_datetime(value: str | None):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
