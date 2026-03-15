"""Agent factory for the Receipt-Pal analytics PoC.

Builds an ``Agent[ReceiptPalContext]`` wired with the three analytics tools
and loaded with the prompt from ``prompts/analytics_system_prompt.md``.
Supports both OpenAI and Gemini (via the OpenAI-compatible endpoint).
"""

from __future__ import annotations

import os
from pathlib import Path

from agents import Agent, set_default_openai_client, set_default_openai_api
from openai import AsyncOpenAI

from context import ReceiptPalContext
from tools import search_receipts, run_query, answer_faq

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "analytics_system_prompt.md"


def _load_instructions() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _configure_provider() -> str:
    """Configure the underlying model provider and return the model name.

    Priority:
    1. If OPENAI_API_KEY is set → use OpenAI directly (SDK default).
    2. If GEMINI_API_KEY is set → use Gemini via the OpenAI-compatible endpoint.
    """
    model = os.environ.get("MODEL", "gpt-4o-mini")

    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not openai_key and gemini_key:
        client = AsyncOpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        set_default_openai_client(client)
        set_default_openai_api("chat_completions")
        model = os.environ.get("MODEL", "gemini-2.0-flash")

    return model


def build_agent() -> Agent[ReceiptPalContext]:
    """Return a fully-configured analytics agent."""
    model = _configure_provider()
    instructions = _load_instructions()

    return Agent[ReceiptPalContext](
        name="Receipt-Pal Analytics",
        instructions=instructions,
        model=model,
        tools=[search_receipts, run_query, answer_faq],
    )
