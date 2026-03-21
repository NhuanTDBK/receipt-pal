"""UpdateSettings tool — persists inferred or explicit user preferences."""

from __future__ import annotations

import json
from typing import Literal

from agents import RunContextWrapper, function_tool

from app.repositories import user_settings_repo
from app.services.agent_context import TelegramAgentContext


@function_tool
async def update_settings(
    ctx: RunContextWrapper[TelegramAgentContext],
    language: str | None = None,
    response_preference: Literal["concise", "talkative", "expert"] | None = None,
    location: str | None = None,
) -> str:
    """Save inferred or explicit user preferences.

    Call this silently when you detect a preference from the conversation —
    for example, the user writes in English (→ language="en"), asks for
    shorter replies (→ response_preference="concise"), or mentions their city.

    All fields are optional — only provided fields are updated.
    Changes take effect on the NEXT session launch.
    """
    settings = await user_settings_repo.update_settings(
        ctx.context.db_session,
        user_id=ctx.context.user_id,
        language=language,
        response_preference=response_preference,
        location=location,
    )
    return json.dumps(
        {
            "language": settings.language,
            "response_preference": settings.response_preference,
            "location": settings.location,
            "note": "Settings saved. They will be applied from the next session.",
        },
        ensure_ascii=False,
    )
