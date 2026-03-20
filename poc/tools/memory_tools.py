"""Memory tools for the Receipt Pal parser agent.

Tools:
    set_memory  — Persist a free-text note scoped to the current user.
    get_memory  — Retrieve notes with optional time-range and keyword filters.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select, and_

from agents import function_tool, RunContextWrapper

from models import Memory
from receipt_context import ReceiptParserContext

_TIME_DELTAS: dict[str, timedelta | None] = {
    "last_week":    timedelta(weeks=1),
    "last_month":   timedelta(days=30),
    "last_3_months": timedelta(days=90),
    "last_year":    timedelta(days=365),
    "all":          None,
}


def _require_db(ctx: RunContextWrapper[ReceiptParserContext]) -> str | None:
    """Return an error string if DB context is not available."""
    if ctx.context.session_factory is None or ctx.context.user_id is None:
        return "Memory tools are not available: no database session in context."
    return None


@function_tool
async def set_memory(
    ctx: RunContextWrapper[ReceiptParserContext],
    content: str,
) -> str:
    """Persist a free-text note for the current user.

    Use this to remember information across conversations — preferences,
    recurring merchants, spending habits, or anything the user asks to note.
    """
    if err := _require_db(ctx):
        return err

    with ctx.context.session_factory() as session:
        memory = Memory(
            id=str(uuid.uuid4()),
            user_id=str(ctx.context.user_id),
            content=content,
        )
        session.add(memory)
        session.commit()
        created_at = session.get(Memory, memory.id).created_at

    return json.dumps({
        "status": "saved",
        "content": content,
        "created_at": created_at.isoformat() if created_at else None,
    }, ensure_ascii=False)


@function_tool
async def get_memory(
    ctx: RunContextWrapper[ReceiptParserContext],
    time_range: Literal["last_week", "last_month", "last_3_months", "last_year", "all"] = "last_month",
    queries: list[str] | None = None,
) -> str:
    """Retrieve stored notes for the current user.

    Args:
        time_range: How far back to look (default: last_month).
        queries:    Optional list of keywords — only notes containing ALL
                    keywords (case-insensitive) are returned.

    Returns a JSON array sorted newest-first.
    """
    if err := _require_db(ctx):
        return err

    user_id_str = str(ctx.context.user_id)
    delta = _TIME_DELTAS.get(time_range)

    with ctx.context.session_factory() as session:
        conditions = [Memory.user_id == user_id_str]

        if delta is not None:
            since = datetime.utcnow() - delta
            conditions.append(Memory.created_at >= since)

        if queries:
            for keyword in queries:
                conditions.append(Memory.content.ilike(f"%{keyword}%"))

        rows = session.execute(
            select(Memory)
            .where(and_(*conditions))
            .order_by(Memory.created_at.desc())
        ).scalars().all()

    results = [
        {
            "id": row.id,
            "content": row.content,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    return json.dumps(results, ensure_ascii=False)
