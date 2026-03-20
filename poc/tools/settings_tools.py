"""Settings tool for the Receipt Pal parser agent.

Tool:
    update_settings — Persist inferred or explicit user preferences to the DB.
                      Changes take effect on the next session launch.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from agents import function_tool, RunContextWrapper

from models import UserSettings
from receipt_context import ReceiptParserContext


@function_tool
async def update_settings(
    ctx: RunContextWrapper[ReceiptParserContext],
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
    if ctx.context.session_factory is None or ctx.context.user_id is None:
        return "Settings not available: no database session in context."

    user_id_str = str(ctx.context.user_id)

    with ctx.context.session_factory() as session:
        settings = session.get(UserSettings, user_id_str)
        if settings is None:
            settings = UserSettings(user_id=user_id_str)
            session.add(settings)

        if language is not None:
            settings.language = language
        if response_preference is not None:
            settings.response_preference = response_preference
        if location is not None:
            settings.location = location

        session.commit()
        session.refresh(settings)

        result = {
            "language": settings.language,
            "response_preference": settings.response_preference,
            "location": settings.location,
            "note": "Settings saved. They will be applied from the next session.",
        }

    return json.dumps(result, ensure_ascii=False)
