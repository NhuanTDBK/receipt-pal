"""Receipt parsing service."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langfuse import LangfuseOtelSpanAttributes, observe
from langfuse.openai import AsyncOpenAI
from opentelemetry import trace as otel_trace

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "system_prompt.md"
)


@dataclass
class TokenUsage:
    """Token consumption for a single Gemini API call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "AskUser",
            "description": "Ask one clarification question. For missing/uncertain fields and edit navigation.",
            "parameters": {
                "type": "object",
                "required": ["question", "options"],
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "allow_skip": {"type": "boolean"},
                    "field": {
                        "type": "string",
                        "enum": [
                            "total",
                            "date",
                            "merchant",
                            "category",
                            "line_item",
                            "edit_selection",
                        ],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "SubmitReceipt",
            "description": (
                "Emit structured receipt data. "
                "mode=draft: send full receipt fields, shows card to user. "
                'mode=final: send ONLY {"mode": "final"}.'
            ),
            "parameters": {
                "type": "object",
                "required": ["mode"],
                "properties": {
                    "mode": {"type": "string", "enum": ["draft", "final"]},
                    "merchant": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {
                            "name": {"type": "string"},
                            "address": {"type": "string"},
                        },
                    },
                    "datetime": {"type": "string"},
                    "billing_period": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "name", "amount"],
                            "properties": {
                                "id": {"type": "integer"},
                                "name": {"type": "string"},
                                "name_raw": {"type": "string"},
                                "quantity": {"type": "integer", "default": 1},
                                "unit_price": {"type": "integer"},
                                "amount": {"type": "integer"},
                                "confidence": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "toppings": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "price": {"type": "integer"},
                                        },
                                    },
                                },
                                "modifiers": {
                                    "type": "object",
                                    "properties": {
                                        "sugar_level": {"type": "string"},
                                        "ice_level": {"type": "string"},
                                        "size": {"type": "string"},
                                    },
                                },
                                "food_tags": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "sugary",
                                            "fried",
                                            "healthy",
                                            "alcohol",
                                            "caffeine",
                                            "dairy",
                                            "spicy",
                                            "non_food",
                                        ],
                                    },
                                },
                            },
                        },
                    },
                    "subtotal": {"type": "integer"},
                    "discount": {"type": "integer"},
                    "tax_rate": {"type": "number"},
                    "tax_amount": {"type": "integer"},
                    "total": {"type": "integer"},
                    "currency": {"type": "string", "default": "VND"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "dining",
                            "cafe",
                            "grocery",
                            "convenience",
                            "health",
                            "entertainment",
                            "transport",
                            "utilities",
                            "rent",
                            "other",
                        ],
                    },
                    "source": {
                        "type": "string",
                        "enum": [
                            "paper",
                            "shopeefood",
                            "grabfood",
                            "gofood",
                            "baemin",
                            "app_unknown",
                        ],
                        "default": "paper",
                    },
                    "notes": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "UpdateReceipt",
            "description": (
                "Patch the current draft receipt. Send ONLY the fields that changed. "
                "Items are matched by their [id] shown in the receipt card."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "address": {"type": "string"},
                        },
                    },
                    "datetime": {"type": "string"},
                    "category": {"type": "string"},
                    "currency": {"type": "string"},
                    "subtotal": {"type": "integer"},
                    "discount": {"type": "integer"},
                    "tax_rate": {"type": "number"},
                    "tax_amount": {"type": "integer"},
                    "total": {"type": "integer"},
                    "notes": {"type": "string"},
                    "items": {
                        "type": "array",
                        "description": "Only changed items. Each must include 'id'.",
                        "items": {
                            "type": "object",
                            "required": ["id"],
                            "properties": {
                                "id": {"type": "integer"},
                                "name": {"type": "string"},
                                "quantity": {"type": "integer"},
                                "unit_price": {"type": "integer"},
                                "amount": {"type": "integer"},
                                "toppings": {"type": "array"},
                                "modifiers": {"type": "object"},
                                "food_tags": {"type": "array"},
                            },
                        },
                    },
                },
            },
        },
    },
]

ToolCallback = Callable[[str, dict], Coroutine[Any, Any, str]]


def _load_system_prompt() -> str:
    text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    logger.info("Loaded system prompt from %s", SYSTEM_PROMPT_PATH)
    return text


def _encode_media(images: list[bytes], pdfs: list[bytes]) -> list[dict]:
    """Encode images and PDFs as base64 data URLs for the Gemini vision API."""
    parts: list[dict] = []
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )
    for pdf_bytes in pdfs:
        b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:application/pdf;base64,{b64}"},
            }
        )
    return parts


def _build_messages(
    history: list[dict],
    new_images: list[bytes],
    new_text: str | None,
    new_pdfs: list[bytes] | None = None,
) -> list[dict]:
    """Build the full messages list for the Gemini API call."""
    messages: list[dict] = [{"role": "system", "content": _load_system_prompt()}]
    messages.extend(history)

    user_content: list[dict] = []
    if new_text:
        user_content.append({"type": "text", "text": new_text})
    if new_images or new_pdfs:
        user_content.extend(_encode_media(new_images, new_pdfs or []))

    if user_content:
        messages.append({"role": "user", "content": user_content})

    return messages


class ReceiptParser:
    """Streams Gemini and dispatches AskUser / SubmitReceipt / UpdateReceipt tool calls."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
        )

    @observe(name="receipt-parse")
    async def parse(
        self,
        images: list[bytes],
        history: list[dict],
        new_text: str | None,
        on_tool_call: ToolCallback,
        *,
        pdfs: list[bytes] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[list[dict], TokenUsage]:
        """Call Gemini with images/PDFs + conversation history.

        Tool results are dispatched to `on_tool_call(tool_name, args)`.
        Returns (updated_messages, token_usage) for the caller to persist.

        pdfs:       PDF bytes to include alongside images (Gemini handles both natively).
        session_id: str(conversation.id) — used as Langfuse session_id and DB conversation key.
        user_id:    str(db_user.id)      — forwarded to Langfuse for per-user trace filtering.
        """
        messages = _build_messages(history, images, new_text, new_pdfs=pdfs)

        full_content = ""
        tool_calls_by_idx: dict[int, dict] = {}
        usage = TokenUsage()

        # Attach session / user to the Langfuse trace created by @observe.
        # Uses OTEL span attributes (Langfuse 4.x native); silently skipped when
        # no Langfuse exporter is active (span.is_recording() == False).
        _span = otel_trace.get_current_span()
        if _span.is_recording():
            if session_id:
                _span.set_attribute(
                    LangfuseOtelSpanAttributes.TRACE_SESSION_ID, session_id
                )
            if user_id:
                _span.set_attribute(LangfuseOtelSpanAttributes.TRACE_USER_ID, user_id)

        stream = await self._client.chat.completions.create(
            model=settings.gemini_model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            # chunk.usage is non-None only on the final streaming chunk
            if chunk.usage is not None:
                usage = TokenUsage(
                    input_tokens=chunk.usage.prompt_tokens or 0,
                    output_tokens=chunk.usage.completion_tokens or 0,
                )

            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                full_content += delta.content

            raw_chunk = chunk.model_dump()
            raw_tool_calls = (
                raw_chunk.get("choices", [{}])[0].get("delta", {}).get("tool_calls")
                or []
            )
            for tc_raw in raw_tool_calls:
                idx = tc_raw.get("index", 0)
                if idx not in tool_calls_by_idx:
                    tool_calls_by_idx[idx] = {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                if tc_raw.get("id"):
                    tool_calls_by_idx[idx]["id"] = tc_raw["id"]
                fn = tc_raw.get("function") or {}
                if fn.get("name"):
                    tool_calls_by_idx[idx]["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    tool_calls_by_idx[idx]["function"]["arguments"] += fn["arguments"]
                extra = tc_raw.get("extra_content")
                if extra:
                    tool_calls_by_idx[idx]["extra_content"] = extra

        if usage.total_tokens == 0:
            logger.warning(
                "No token usage returned by Gemini API (session_id=%s).", session_id
            )

        tool_calls = [tool_calls_by_idx[i] for i in sorted(tool_calls_by_idx.keys())]

        assistant_msg: dict = {"role": "assistant", "content": full_content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            try:
                fn_args = (
                    json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                )
            except json.JSONDecodeError:
                fn_args = {}

            result = await on_tool_call(fn_name, fn_args)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                }
            )

        return messages, usage


def apply_update_patch(current: dict, patch: dict) -> dict:
    """Merge a patch from UpdateReceipt into the current draft receipt."""
    updated = dict(current)
    for key, value in patch.items():
        if key == "merchant":
            updated["merchant"] = {**updated.get("merchant", {}), **value}
        elif key == "items":
            items = [dict(item) for item in updated.get("items", [])]
            for item_patch in value:
                patch_id = item_patch.get("id")
                for item in items:
                    if item.get("id") == patch_id:
                        item.update({k: v for k, v in item_patch.items() if k != "id"})
                        break
            updated["items"] = items
        else:
            updated[key] = value
    return updated


def assign_item_ids(receipt: dict) -> dict:
    """Assign sequential integer IDs to items for UpdateReceipt patch matching."""
    receipt = dict(receipt)
    for i, item in enumerate(receipt.get("items", []), start=1):
        item["id"] = i
    return receipt
