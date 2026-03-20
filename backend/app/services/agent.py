"""Agent factory for the Receipt-Pal Telegram bot.

Provides:
    configure_provider()          — configures SDK for Gemini.
    build_receipt_agent(settings) — parser + analytics agent with settings.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from agents import Agent, set_default_openai_api, set_tracing_disabled

from app.config import settings as app_settings
from app.services.agent_context import TelegramAgentContext
from app.services.tools import (
    answer_faq,
    ask_user,
    run_query,
    search_receipts,
    set_memory,
    submit_receipt_draft,
    submit_receipt_final,
    update_receipt,
    update_settings,
)

logger = logging.getLogger(__name__)

_PARSER_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "system_prompt.md"
)
_ANALYTICS_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "analytics_instructions.md"
)

_TELEGRAM_NOTE = (
    "\n\n---\n\n"
    "NOTE: The user is interacting via Telegram.\n\n"
    "HOW TOOLS WORK IN TELEGRAM:\n"
    "- ask_user: displays your question with inline keyboard buttons. "
    "The user's answer will arrive as a separate message in the next turn.\n"
    "- submit_receipt_draft: sends the receipt card with confirm/edit/cancel buttons. "
    "The user responds with a button press in the next turn.\n"
    "- update_receipt: send a patch with ONLY changed fields. "
    "For items, include only changed items with their [id].\n"
    "- submit_receipt_final: saves the confirmed receipt to the database.\n\n"
    "IMPORTANT: After calling ask_user or submit_receipt_draft, STOP. "
    "Do NOT continue processing — the user's response will come in the next turn.\n"
    "IMPORTANT: Only call ONE tool per response."
)


def _build_settings_header(user_settings) -> str:
    """Build the ## Current Settings block prepended to instructions."""
    lines = [
        "## Current Settings",
        f"- Language: {user_settings.language} "
        "— respond in this language for all replies",
        f"- Response style: {user_settings.response_preference}",
    ]
    if user_settings.location:
        lines.append(f"- Location: {user_settings.location}")
    lines.append("")
    return "\n".join(lines) + "\n---\n\n"


def configure_provider() -> None:
    """Apply SDK-level settings for Gemini compatibility.

    Sets the Agents SDK to use the chat_completions API (required for
    non-OpenAI providers) and disables the built-in tracing to avoid
    401 errors from the OpenAI tracing platform.
    """
    os.environ.setdefault("OPENAI_API_KEY", app_settings.openai_api_key)
    os.environ.setdefault("OPENAI_BASE_URL", app_settings.openai_base_url)

    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)
    logger.info(
        "Agents SDK configured: model=%s, base_url=%s",
        app_settings.model,
        app_settings.openai_base_url,
    )


def build_receipt_agent(user_settings=None) -> Agent[TelegramAgentContext]:
    """Return the fully-configured receipt + analytics agent.

    Args:
        user_settings: UserSettings ORM instance. If provided, settings are
                       injected into the static instructions header.
    """
    base_prompt = _PARSER_PROMPT_PATH.read_text(encoding="utf-8")
    analytics_prompt = _ANALYTICS_PROMPT_PATH.read_text(encoding="utf-8")

    if user_settings is not None:
        header = _build_settings_header(user_settings)
        instructions = header + base_prompt + _TELEGRAM_NOTE + "\n\n" + analytics_prompt
    else:
        instructions = base_prompt + _TELEGRAM_NOTE + "\n\n" + analytics_prompt

    return Agent[TelegramAgentContext](
        name="Receipt-Pal",
        instructions=instructions,
        model=app_settings.model,
        tools=[
            ask_user,
            submit_receipt_draft,
            submit_receipt_final,
            update_receipt,
            set_memory,
            update_settings,
            search_receipts,
            run_query,
            answer_faq,
        ],
    )
