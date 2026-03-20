"""Receipt-Pal Analytics CLI — interactive analytics assistant.

Usage:
    cd poc
    uv run python analytics_cli.py

Environment variables (see .env.example):
    OPENAI_API_KEY   — OpenAI API key  (OR use GEMINI_API_KEY for Gemini)
    GEMINI_API_KEY   — Gemini API key  (optional alternative)
    MODEL            — model name      (default: gpt-4o-mini / gemini-2.0-flash)
    POC_USER_ID      — fixed PoC user UUID (default: 00000000-0000-0000-0000-000000000001)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Allow importing sibling modules (context, models, db, agent, tools)
sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv()

from agents import Runner
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent, AgentUpdatedStreamEvent
from agents.items import (
    MessageOutputItem,
    ReasoningItem,
    ToolCallItem,
    ToolCallOutputItem,
)

from agent import build_agent, configure_provider
from context import ReceiptPalContext
from db import init_db

_DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"

# ── ANSI colours ──────────────────────────────────────────────────────────────
_GREY   = "\033[90m"
_CYAN   = "\033[96m"
_YELLOW = "\033[93m"
_GREEN  = "\033[92m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"


def _resolve_user_id() -> uuid.UUID:
    raw = os.environ.get("POC_USER_ID", _DEFAULT_USER_ID)
    try:
        return uuid.UUID(raw)
    except ValueError:
        print(f"  ⚠  POC_USER_ID '{raw}' is not a valid UUID. Using default.")
        return uuid.UUID(_DEFAULT_USER_ID)


def _validate_env() -> None:
    configure_provider()


def _banner(user_id: uuid.UUID, receipt_count: int) -> None:
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║      Receipt-Pal Analytics CLI (PoC)         ║")
    print("  ╠══════════════════════════════════════════════╣")
    print(f"  ║  User  : {str(user_id)[:36]:<36}║")
    print(f"  ║  Loaded: {receipt_count:<3} receipts in local DB           ║")
    print("  ╠══════════════════════════════════════════════╣")
    print("  ║  Tools : search · query · faq                ║")
    print("  ║  Type a question or 'quit' to exit.          ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()


def _fmt_args(raw_args: str, max_len: int = 120) -> str:
    """Pretty-print tool arguments, truncated for display."""
    try:
        parsed = json.loads(raw_args)
        out = json.dumps(parsed, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        out = raw_args or ""
    return out if len(out) <= max_len else out[:max_len] + "…"


def _fmt_output(output: object, max_len: int = 160) -> str:
    """Compact representation of a tool return value."""
    if isinstance(output, str):
        text = output
    else:
        try:
            text = json.dumps(output, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(output)
    return text if len(text) <= max_len else text[:max_len] + "…"


async def _stream_turn(
    agent,
    history: list,
    ctx: ReceiptPalContext,
) -> list:
    """Run one agent turn with streaming output.

    Displays:
    - 💭 thinking tokens (if the model emits them via ReasoningItem)
    - 🔧 tool name + truncated arguments for each tool call
    - ↳  truncated tool result after each call
    - Streamed text tokens for the final assistant reply

    Returns the updated input list for the next turn.
    """
    thinking_shown = False
    text_started = False
    pending_newline = False  # track whether we need to print a newline before new sections

    print(f"  {_DIM}💭 thinking…{_RESET}", end="", flush=True)

    stream = Runner.run_streamed(agent, history, context=ctx)
    async for event in stream.stream_events():

        # ── Reasoning / thinking tokens ──────────────────────────────────
        if isinstance(event, RunItemStreamEvent):
            item = event.item

            if isinstance(item, ReasoningItem):
                # Surface the model's internal reasoning summary if present.
                summary = getattr(item.raw_item, "summary", None) or []
                for chunk in summary:
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        if not thinking_shown:
                            print(f"\r  {_DIM}💭{_RESET} ", end="", flush=True)
                            thinking_shown = True
                        print(f"{_DIM}{text}{_RESET}", end="", flush=True)

            # ── Tool selection ────────────────────────────────────────────
            elif isinstance(item, ToolCallItem):
                raw = item.raw_item
                tool_name = getattr(raw, "name", "?")
                raw_args  = getattr(raw, "arguments", "") or ""

                if not text_started:
                    # Clear the "thinking…" line
                    print(f"\r{' ' * 30}\r", end="", flush=True)
                else:
                    print()

                print(
                    f"  {_CYAN}🔧 {_BOLD}{tool_name}{_RESET}"
                    f"{_GREY}({_fmt_args(raw_args)}){_RESET}"
                )
                pending_newline = False
                text_started = False

            # ── Tool result ───────────────────────────────────────────────
            elif isinstance(item, ToolCallOutputItem):
                output_str = _fmt_output(item.output)
                print(f"  {_GREY}   ↳ {output_str}{_RESET}")
                pending_newline = False

        # ── Streaming text tokens ─────────────────────────────────────────
        elif isinstance(event, RawResponsesStreamEvent):
            data = event.data

            # Chat-completions API (Gemini / OpenAI chat_completions mode)
            if hasattr(data, "choices") and data.choices:
                delta = data.choices[0].delta
                token = getattr(delta, "content", None) or ""
                if token:
                    if not text_started:
                        print(f"\r  {_GREEN}{_BOLD}Bot:{_RESET} ", end="", flush=True)
                        text_started = True
                    print(token, end="", flush=True)
                    pending_newline = True

            # Responses API (OpenAI native streaming)
            elif hasattr(data, "type"):
                if data.type == "response.output_text.delta":
                    token = getattr(data, "delta", "") or ""
                    if token:
                        if not text_started:
                            print(f"\r  {_GREEN}{_BOLD}Bot:{_RESET} ", end="", flush=True)
                            text_started = True
                        print(token, end="", flush=True)
                        pending_newline = True

    if pending_newline:
        print()
    elif not text_started:
        # Model replied with no text (e.g. only tool calls with no follow-up)
        final = stream.final_output or ""
        if final:
            print(f"\r  {_GREEN}{_BOLD}Bot:{_RESET} {final}")
        else:
            print(f"\r{' ' * 30}")  # clear spinner

    print()
    return stream.to_input_list()


async def chat_loop() -> None:
    _validate_env()

    user_id = _resolve_user_id()
    session_factory = init_db(user_id)

    from sqlalchemy import select, func
    from models import Receipt

    with session_factory() as s:
        count = s.execute(
            select(func.count(Receipt.id)).where(Receipt.user_id == str(user_id))
        ).scalar_one()

    ctx = ReceiptPalContext(user_id=user_id, session_factory=session_factory)
    agent = build_agent()

    _banner(user_id, count)

    history: list = []

    while True:
        try:
            user_input = (await asyncio.to_thread(input, "  You: ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("  Goodbye!")
            break

        history.append({"role": "user", "content": user_input})

        try:
            history = await _stream_turn(agent, history, ctx)
        except KeyboardInterrupt:
            print("\n  Interrupted.")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"\r  ❌ Error: {exc}")
            history.pop()
            continue


def main() -> None:
    asyncio.run(chat_loop())


if __name__ == "__main__":
    main()
