"""AskUser tool — sends a Telegram inline keyboard and returns immediately."""

from __future__ import annotations

from typing import Literal

from agents import RunContextWrapper, function_tool

from app.presentation.bot.keyboards.receipt import ask_user_keyboard
from app.services.agent_context import TelegramAgentContext


@function_tool
async def ask_user(
    ctx: RunContextWrapper[TelegramAgentContext],
    question: str,
    options: list[str],
    allow_skip: bool = True,
    field: Literal[
        "total",
        "date",
        "merchant",
        "category",
        "line_item",
        "edit_selection",
    ]
    | None = None,
) -> str:
    """Ask one clarification question and display options to the user.

    Sends an inline keyboard to Telegram. The user's answer will arrive
    as a separate callback event and be fed into the next agent run.
    """
    tc = ctx.context
    await tc.status_msg.edit_text(
        f"❓ {question}",
        reply_markup=ask_user_keyboard(options, allow_skip),
    )
    return "Question shown to user. Awaiting their answer."
