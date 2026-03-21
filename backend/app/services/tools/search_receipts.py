"""Search tool — keyword / filter search over the current user's receipts.

``user_id`` is taken exclusively from the run context and is never exposed
as a tool parameter so the model cannot request data belonging to other users.
"""

from __future__ import annotations

import json
from typing import Annotated

from agents import RunContextWrapper, function_tool
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.models.receipt import Receipt, ReceiptItem
from app.services.agent_context import TelegramAgentContext


@function_tool
async def search_receipts(
    ctx: RunContextWrapper[TelegramAgentContext],
    query: Annotated[
        str, "Keyword or phrase to search for (merchant name, item name, category, …)"
    ],
    category: Annotated[
        str | None,
        "Optional category filter: dining, cafe, grocery, convenience, health, entertainment, transport, utilities, rent, other",
    ] = None,
    limit: Annotated[int, "Maximum number of receipts to return (1–20)"] = 10,
) -> str:
    """Search the user's receipts by keyword and optional category filter.

    Returns a JSON array of matching receipts with their items.
    Use this tool when the user asks about specific purchases, merchants,
    or wants to find receipts matching a description.
    """
    user_id = ctx.context.user_id
    limit = max(1, min(limit, 20))
    session = ctx.context.db_session

    stmt = (
        select(Receipt)
        .where(Receipt.user_id == user_id)
        .options(selectinload(Receipt.items))
    )

    if category:
        stmt = stmt.where(Receipt.category == category)

    if query.strip():
        q = f"%{query.strip()}%"
        stmt = (
            stmt.join(Receipt.items, isouter=True)
            .where(
                or_(
                    Receipt.merchant_name.ilike(q),
                    Receipt.category.ilike(q),
                    ReceiptItem.name.ilike(q),
                )
            )
            .distinct()
        )

    stmt = stmt.order_by(Receipt.receipt_datetime.desc()).limit(limit)
    result = await session.execute(stmt)
    receipts = result.scalars().unique().all()

    results = []
    for r in receipts:
        results.append(
            {
                "id": str(r.id),
                "merchant": r.merchant_name,
                "address": r.merchant_address,
                "date": r.receipt_datetime.isoformat() if r.receipt_datetime else None,
                "category": r.category,
                "total": r.total,
                "currency": r.currency,
                "items": [
                    {
                        "name": item.name,
                        "quantity": item.quantity,
                        "amount": item.amount,
                        "food_tags": item.food_tags or [],
                    }
                    for item in r.items
                ],
            }
        )

    if not results:
        return json.dumps(
            {"found": 0, "receipts": [], "note": "No receipts matched the search."}
        )

    return json.dumps({"found": len(results), "receipts": results}, ensure_ascii=False)
