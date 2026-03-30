"""Agent factory for the Receipt-Pal PoC.

Provides:
    configure_provider()         — Call once at startup; reads OPENAI_BASE_URL from env.
    build_agent()                — Analytics agent (search, query, FAQ)
    build_receipt_agent(settings) — Parser agent; settings injected into static instructions.

Provider is configured entirely via environment variables:
    OPENAI_API_KEY   required
    OPENAI_BASE_URL  optional — when set, switches to chat_completions API and disables tracing
    MODEL            optional model name (default: gpt-4o-mini)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agents import Agent, set_default_openai_api, set_tracing_disabled

from context import ReceiptPalContext
from receipt_context import ReceiptParserContext
from schema_generator import build_analytics_prompt
from tools import search_receipts, run_query, answer_faq
from tools.receipt_tools import (
    ask_user,
    submit_receipt_draft,
    submit_receipt_final,
    update_receipt,
)
from tools.memory_tools import set_memory
from tools.settings_tools import update_settings

_ANALYTICS_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "analytics_system_prompt.md"
)
_PARSER_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "system_prompt.md"
)

_CLI_NOTE = (
    "\n\n---\n\n"
    "NOTE: The user is interacting via a terminal CLI, not Telegram. "
    "There are no inline keyboard buttons.\n\n"
    "HOW TOOLS WORK IN CLI:\n"
    "- ask_user: displays your question and numbered options, then waits for input. "
    "The user's answer is returned as the tool result immediately — continue in the same turn.\n"
    "- submit_receipt_draft: send the full parsed receipt object. CLI assigns [id] to each "
    "item and shows the card. User replies 'confirm', 'edit', or describes changes.\n"
    "- update_receipt: send a patch object with ONLY changed fields. For items, include only "
    "changed items with their [id] from the card. CLI re-displays the updated card.\n"
    "- submit_receipt_final: call with NO arguments — CLI saves the stored draft automatically.\n\n"
    "EDIT FLOW: submit_receipt_draft → user says what to change → "
    "update_receipt(patch) → repeat until user confirms → submit_receipt_final.\n\n"
    "IMPORTANT: Only call ONE tool per response. Do not chain tools in a single turn."
)

_MODEL = os.environ.get("MODEL", "gpt-4o-mini")


def _build_settings_header(settings) -> str:
    """Build the ## Current Settings block prepended to the parser agent instructions."""
    lines = [
        "## Current Settings",
        f"- Language: {settings.language} — respond in this language for all replies",
        f"- Response style: {settings.response_preference}",
    ]
    if settings.location:
        lines.append(f"- Location: {settings.location}")
    lines.append("")
    return "\n".join(lines) + "\n---\n\n"


def configure_provider() -> None:
    """Apply SDK-level settings based on environment variables.

    When OPENAI_BASE_URL is set (any custom endpoint), switches the SDK to the
    chat_completions API (required for non-OpenAI providers) and disables tracing
    so the non-OpenAI key doesn't trigger noisy 401 errors from the trace platform.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set. Create a .env file or export it.")
        sys.exit(1)
    if os.environ.get("OPENAI_BASE_URL"):
        set_default_openai_api("chat_completions")
        set_tracing_disabled(True)


def build_agent() -> Agent[ReceiptPalContext]:
    """Return the fully-configured analytics agent with dynamic schema."""
    instructions = build_analytics_prompt(str(_ANALYTICS_PROMPT_PATH))
    return Agent[ReceiptPalContext](
        name="Receipt-Pal Analytics",
        instructions=instructions,
        model=_MODEL,
        tools=[search_receipts, run_query, answer_faq],
    )


def build_receipt_agent(settings) -> Agent[ReceiptParserContext]:
    """Return the fully-configured receipt parser agent.

    Args:
        settings: UserSettings ORM instance loaded at session start.
                  Injected once into static instructions — changes saved mid-session
                  via update_settings take effect on the next launch.
    """
    base_prompt = _PARSER_PROMPT_PATH.read_text(encoding="utf-8")
    instructions = _build_settings_header(settings) + base_prompt + _CLI_NOTE
    return Agent[ReceiptParserContext](
        name="Receipt-Pal Parser",
        instructions=instructions,
        model=_MODEL,
        tools=[
            ask_user,
            submit_receipt_draft,
            submit_receipt_final,
            update_receipt,
            set_memory,
            update_settings,
        ],
    )
