"""SetMemory tool — persists a free-text note for the current user."""

from __future__ import annotations

import json

from agents import RunContextWrapper, function_tool

from app.repositories import memory_repo
from app.services.agent_context import TelegramAgentContext


@function_tool
async def set_memory(
    ctx: RunContextWrapper[TelegramAgentContext],
    content: str,
) -> str:
    """Persist a free-text note for the current user.

    Use this to remember information across conversations — preferences,
    recurring merchants, spending habits, or anything the user asks to note.
    """
    memory = await memory_repo.create_memory(
        ctx.context.db_session,
        user_id=ctx.context.user_id,
        content=content,
    )
    return json.dumps({
        "status": "saved",
        "content": content,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
    }, ensure_ascii=False)
