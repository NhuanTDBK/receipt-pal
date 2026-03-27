"""Search tool — keyword / filter search over the current user's receipts.

``user_id`` is taken exclusively from the run context and is never exposed
as a tool parameter so the model cannot request data belonging to other users.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from agents import RunContextWrapper, function_tool
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.models.receipt import Receipt, ReceiptItem
from app.services.agent_context import TelegramAgentContext


def _parse_iso_bound(value: str, *, is_end: bool) -> datetime:
    """Parse ISO 8601 date/datetime into a timezone-aware bound."""
    raw = value.strip()
    if not raw:
        raise ValueError("Date value cannot be empty.")

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed_dt = datetime.fromisoformat(normalized)
    except ValueError:
        parsed_date = date.fromisoformat(raw)
        parsed_time = time.max if is_end else time.min
        return datetime.combine(parsed_date, parsed_time, tzinfo=timezone.utc)

    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
    return parsed_dt


def _parse_relative_bound(value: str, *, is_end: bool) -> datetime | None:
    """Parse relative date phrases into timezone-aware datetime bounds."""
    text = value.strip().lower()
    if not text:
        return None

    now = datetime.now(timezone.utc)
    today = now.date()

    if text == "today":
        return datetime.combine(
            today, time.max if is_end else time.min, tzinfo=timezone.utc
        )

    if text == "yesterday":
        day = today - timedelta(days=1)
        return datetime.combine(
            day, time.max if is_end else time.min, tzinfo=timezone.utc
        )

    if text == "this week":
        week_start = today - timedelta(days=today.weekday())
        return (
            now
            if is_end
            else datetime.combine(week_start, time.min, tzinfo=timezone.utc)
        )

    if text == "last week":
        this_week_start = today - timedelta(days=today.weekday())
        last_week_start = this_week_start - timedelta(days=7)
        last_week_end = this_week_start - timedelta(days=1)
        return datetime.combine(
            last_week_end if is_end else last_week_start,
            time.max if is_end else time.min,
            tzinfo=timezone.utc,
        )

    if text == "this month":
        month_start = date(today.year, today.month, 1)
        return (
            now
            if is_end
            else datetime.combine(month_start, time.min, tzinfo=timezone.utc)
        )

    if text == "last month":
        first_this_month = date(today.year, today.month, 1)
        last_day_prev_month = first_this_month - timedelta(days=1)
        first_day_prev_month = date(
            last_day_prev_month.year, last_day_prev_month.month, 1
        )
        return datetime.combine(
            last_day_prev_month if is_end else first_day_prev_month,
            time.max if is_end else time.min,
            tzinfo=timezone.utc,
        )

    range_match = re.fullmatch(r"(?:last|past)\s+(\d+)\s+days?", text)
    if range_match:
        days = int(range_match.group(1))
        if days <= 0:
            raise ValueError("Relative day ranges must be greater than zero.")
        return now if is_end else now - timedelta(days=days)

    ago_match = re.fullmatch(r"(\d+)\s+days?\s+ago", text)
    if ago_match:
        days = int(ago_match.group(1))
        target_day = today - timedelta(days=days)
        return datetime.combine(
            target_day,
            time.max if is_end else time.min,
            tzinfo=timezone.utc,
        )

    return None


def _parse_date_bound(value: str, *, is_end: bool) -> datetime:
    relative = _parse_relative_bound(value, is_end=is_end)
    if relative is not None:
        return relative
    return _parse_iso_bound(value, is_end=is_end)


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
    start_date: Annotated[
        str | None,
        "Optional lower bound on receipt_datetime. Supports ISO 8601 plus relative phrases (today, yesterday, this week, last week, this month, last month, last N days, N days ago)",
    ] = None,
    end_date: Annotated[
        str | None,
        "Optional upper bound on receipt_datetime. Supports ISO 8601 plus relative phrases (today, yesterday, this week, last week, this month, last month, last N days, N days ago)",
    ] = None,
    limit: Annotated[int, "Maximum number of receipts to return (1–20)"] = 10,
) -> str:
    """Search the user's receipts by keyword, optional category, and date range.

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

    try:
        start_dt = _parse_date_bound(start_date, is_end=False) if start_date else None
        end_dt = _parse_date_bound(end_date, is_end=True) if end_date else None
    except ValueError as exc:
        return json.dumps({"error": f"Invalid date filter: {exc}"})

    if start_dt is not None and end_dt is not None and start_dt > end_dt:
        return json.dumps(
            {"error": "Invalid date filter: start_date must be <= end_date."}
        )

    if start_dt is not None:
        stmt = stmt.where(Receipt.receipt_datetime >= start_dt)
    if end_dt is not None:
        stmt = stmt.where(Receipt.receipt_datetime <= end_dt)

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
