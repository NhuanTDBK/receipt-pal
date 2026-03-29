"""Receipt Pal CLI PoC — Interactive receipt parsing with OpenAI Agents SDK."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv()

from agents import Runner
from agents.stream_events import (
    RawResponsesStreamEvent,
    RunItemStreamEvent,
)
from agents.items import (
    ReasoningItem,
    ToolCallItem,
    ToolCallOutputItem,
)

from agent import build_receipt_agent, configure_provider
from db import init_db, load_or_create_settings
from receipt_context import ReceiptParserContext

_DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"

# ── ANSI colours ──────────────────────────────────────────────────────────────
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_GREY = "\033[90m"
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_env() -> None:
    configure_provider()


def _resolve_user_id() -> uuid.UUID:
    raw = os.environ.get("POC_USER_ID", _DEFAULT_USER_ID)
    try:
        return uuid.UUID(raw)
    except ValueError:
        print(f"  ⚠  POC_USER_ID '{raw}' is not a valid UUID. Using default.")
        return uuid.UUID(_DEFAULT_USER_ID)


def _encode_image(image_path: str) -> dict:
    """Encode a local image as a base64 data URL for the vision API."""
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(path.suffix.lower(), "image/jpeg")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}


def _fmt_args(raw_args: str, max_len: int = 120) -> str:
    try:
        parsed = json.loads(raw_args)
        out = json.dumps(parsed, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        out = raw_args or ""
    return out if len(out) <= max_len else out[:max_len] + "…"


def _fmt_output(output: object, max_len: int = 160) -> str:
    if isinstance(output, str):
        text = output
    else:
        try:
            text = json.dumps(output, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(output)
    return text if len(text) <= max_len else text[:max_len] + "…"


# ---------------------------------------------------------------------------
# Streaming turn
# ---------------------------------------------------------------------------


async def _stream_turn(
    agent,
    history: list,
    ctx: ReceiptParserContext,
) -> list:
    """Run one agent turn with streaming output. Returns the updated history."""
    text_started = False
    pending_newline = False

    print(f"  {_DIM}💭 thinking…{_RESET}", end="", flush=True)

    stream = Runner.run_streamed(agent, history, context=ctx)
    async for event in stream.stream_events():
        if isinstance(event, RunItemStreamEvent):
            item = event.item

            if isinstance(item, ReasoningItem):
                summary = getattr(item.raw_item, "summary", None) or []
                for chunk in summary:
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        print(f"\r  {_DIM}💭 {text}{_RESET}", end="", flush=True)

            elif isinstance(item, ToolCallItem):
                raw = item.raw_item
                tool_name = getattr(raw, "name", "?")
                raw_args = getattr(raw, "arguments", "") or ""
                print(f"\r{' ' * 30}\r", end="", flush=True)
                print(
                    f"  {_CYAN}🔧 {_BOLD}{tool_name}{_RESET}"
                    f"{_GREY}({_fmt_args(raw_args)}){_RESET}"
                )
                text_started = False
                pending_newline = False

            elif isinstance(item, ToolCallOutputItem):
                print(f"  {_GREY}   ↳ {_fmt_output(item.output)}{_RESET}")
                pending_newline = False

        elif isinstance(event, RawResponsesStreamEvent):
            data = event.data
            token = ""

            if hasattr(data, "choices") and data.choices:
                token = getattr(data.choices[0].delta, "content", None) or ""
            elif hasattr(data, "type") and data.type == "response.output_text.delta":
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
        final = stream.final_output or ""
        if final:
            print(f"\r  {_GREEN}{_BOLD}Bot:{_RESET} {final}")
        else:
            print(f"\r{' ' * 30}")

    print()
    return stream.to_input_list()


# ---------------------------------------------------------------------------
# Chat loop
# ---------------------------------------------------------------------------


async def chat_loop() -> None:
    _validate_env()

    user_id = _resolve_user_id()
    session_factory = init_db(user_id)
    settings = load_or_create_settings(session_factory, user_id)

    agent = build_receipt_agent(settings)
    ctx = ReceiptParserContext(
        user_id=user_id,
        session_factory=session_factory,
        settings=settings,
    )
    history: list = []

    lang = settings.language
    style = settings.response_preference
    location = settings.location or "—"

    print()
    print("  ╔════════════════════════════════════════════════╗")
    print("  ║           Receipt Pal CLI (PoC)                ║")
    print("  ╠════════════════════════════════════════════════╣")
    print(f"  ║  User    : {str(user_id)[:36]:<36}║")
    print(f"  ║  Language: {lang:<36}  ║")
    print(f"  ║  Style   : {style:<36}  ║")
    print(f"  ║  Location: {location:<36}  ║")
    print("  ╠════════════════════════════════════════════════╣")
    print("  ║  Send a receipt image path to parse it.        ║")
    print("  ║  Or type purchases to log them directly.       ║")
    print("  ║  Type 'quit' to exit.                          ║")
    print("  ╚════════════════════════════════════════════════╝")
    print()

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

        # Build message content — image or plain text
        potential_path = Path(user_input.strip("'\"")).expanduser()
        if (
            potential_path.exists()
            and potential_path.suffix.lower() in IMAGE_EXTENSIONS
        ):
            try:
                image_content = _encode_image(str(potential_path))
                content: str | list = [
                    {
                        "type": "text",
                        "text": "Here is a receipt photo. Please parse it.",
                    },
                    image_content,
                ]
            except FileNotFoundError as e:
                print(f"  Error: {e}")
                continue
        else:
            content = user_input

        history.append({"role": "user", "content": content})

        try:
            history = await _stream_turn(agent, history, ctx)
        except KeyboardInterrupt:
            print("\n  Interrupted.")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"\r  ❌ Error: {exc}")
            history.pop()
            continue


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    asyncio.run(chat_loop())


if __name__ == "__main__":
    main()
