"""Smoke-test: verify that @observe + OTEL span attributes pattern does not raise TypeError.

Usage (from repo root):
    python backend/scripts/test_langfuse_kwargs.py

The script loads backend/.env, creates a langfuse-wrapped AsyncOpenAI client
identical to the one used in ReceiptParser, and makes a minimal chat completion
call via the @observe-decorated helper — exactly what would happen in production.

Exit code 0  → no TypeError, fix is working.
Exit code 1  → unexpected error (printed to stderr).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Load backend/.env before any app imports so settings pick up env vars.
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Ensure backend/ is on the Python path when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langfuse import LangfuseOtelSpanAttributes, observe  # noqa: E402
from langfuse.openai import AsyncOpenAI  # noqa: E402
from opentelemetry import trace as otel_trace  # noqa: E402

from app.config import settings  # noqa: E402


@observe(name="smoke-test-receipt-parse")
async def _call(client: AsyncOpenAI) -> None:
    _span = otel_trace.get_current_span()
    if _span.is_recording():
        _span.set_attribute(LangfuseOtelSpanAttributes.TRACE_SESSION_ID, "test-session-123")
        _span.set_attribute(LangfuseOtelSpanAttributes.TRACE_USER_ID, "test-user-456")

    stream = await client.chat.completions.create(
        model=settings.gemini_model,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        stream=True,
        stream_options={"include_usage": True},
    )
    response = ""
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            response += chunk.choices[0].delta.content
    print(f"✓ Model replied: {response.strip()!r}")
    print("✓ No TypeError — @observe + OTEL span attribute fix is working correctly.")


async def main() -> None:
    client = AsyncOpenAI(
        api_key=settings.gemini_api_key,
        base_url=settings.gemini_base_url,
    )
    await _call(client)


if __name__ == "__main__":
    asyncio.run(main())
