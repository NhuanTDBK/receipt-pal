"""@function_tool implementations for the Receipt Pal parser agent.

Tools:
    ask_user              – Ask a clarification question and wait for the user's answer.
    submit_receipt_draft  – Parse and display a draft receipt card.
    submit_receipt_final  – Save the current draft to disk.
    update_receipt        – Patch the current draft and re-display.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime as _datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from agents import function_tool, RunContextWrapper

from receipt_context import ReceiptParserContext

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RECEIPTS_DIR = PROJECT_ROOT / "data" / "receipts"


# ---------------------------------------------------------------------------
# Pydantic models for structured receipt data
# ---------------------------------------------------------------------------


class MerchantInfo(BaseModel):
    name: str
    address: str | None = None


class ItemTopping(BaseModel):
    name: str
    price: int = 0


class ItemModifiers(BaseModel):
    sugar_level: str | None = None
    ice_level: str | None = None
    size: str | None = None


class ReceiptItem(BaseModel):
    name: str
    amount: int
    name_raw: str | None = None
    quantity: int = 1
    unit_price: int | None = None
    confidence: Literal["high", "medium", "low"] = "high"
    toppings: list[ItemTopping] = []
    modifiers: ItemModifiers | None = None
    food_tags: list[
        Literal[
            "sugary", "fried", "healthy", "alcohol",
            "caffeine", "dairy", "spicy", "non_food",
        ]
    ] = []


class ReceiptData(BaseModel):
    """Full receipt payload for draft submission."""

    merchant: MerchantInfo | None = None
    datetime: str | None = None
    billing_period: str | None = None
    items: list[ReceiptItem] = []
    subtotal: int | None = None
    discount: int | None = None
    tax_rate: float | None = None
    tax_amount: int | None = None
    total: int | None = None
    currency: str = "VND"
    category: Literal[
        "dining", "cafe", "grocery", "convenience", "health",
        "entertainment", "transport", "utilities", "rent", "other",
    ] | None = None
    source: Literal[
        "paper", "shopeefood", "grabfood", "gofood", "baemin", "app_unknown"
    ] = "paper"


class ItemPatch(BaseModel):
    """Item update — `id` is required to identify which item to patch."""

    id: int
    name: str | None = None
    quantity: int | None = None
    unit_price: int | None = None
    amount: int | None = None
    toppings: list[ItemTopping] | None = None
    modifiers: ItemModifiers | None = None
    food_tags: list[str] | None = None


class ReceiptPatch(BaseModel):
    """Sparse patch for the current draft. Only include changed fields."""

    merchant: MerchantInfo | None = None
    datetime: str | None = None
    category: Literal[
        "dining", "cafe", "grocery", "convenience", "health",
        "entertainment", "transport", "utilities", "rent", "other",
    ] | None = None
    currency: str | None = None
    subtotal: int | None = None
    discount: int | None = None
    tax_rate: float | None = None
    tax_amount: int | None = None
    total: int | None = None
    notes: str | None = None
    items: list[ItemPatch] | None = None


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _fmt_vnd(amount: int) -> str:
    return f"{amount:,}d".replace(",", ".")


def _fmt_currency(amount: int, currency: str = "VND") -> str:
    if currency == "VND":
        return _fmt_vnd(amount)
    return f"{amount:,} {currency}"


def display_receipt_card(receipt: dict, mode: str) -> None:
    """Print a formatted receipt card to the terminal."""
    merchant = receipt.get("merchant") or {}
    merchant_name = merchant.get("name", "Unknown")
    merchant_addr = merchant.get("address", "")
    dt = receipt.get("datetime", "")
    category = receipt.get("category", "")
    currency = receipt.get("currency", "VND")
    total = receipt.get("total") or 0

    label = "[DRAFT]" if mode == "draft" else "[SAVED]"

    print()
    print(f"  ┌─── {label} {'─' * (40 - len(label))}┐")
    print(f"  │ 🧾 {merchant_name}")
    if merchant_addr:
        print(f"  │    {merchant_addr}")
    print(f"  │ 📅 {dt}  •  {category}")
    print(f"  │{'─' * 45}│")

    for item in receipt.get("items", []):
        item_id = item.get("id", "")
        name = item.get("name", "???")
        qty = item.get("quantity", 1)
        amount = item.get("amount") or 0
        qty_str = f"{qty}x " if qty > 1 else ""
        id_str = f"[{item_id}] " if item_id != "" else ""
        amount_str = _fmt_currency(amount, currency)
        line = f"{id_str}{qty_str}{name}"
        print(f"  │ {line:<32} {amount_str:>10} │")

        for topping in item.get("toppings") or []:
            tp_name = topping.get("name", "")
            tp_price = topping.get("price") or 0
            price_str = f"+{_fmt_currency(tp_price, currency)}" if tp_price else "free"
            print(f"  │   + {tp_name:<28} {price_str:>10} │")

        modifiers = item.get("modifiers") or {}
        if modifiers:
            mod_parts = []
            if modifiers.get("sugar_level"):
                mod_parts.append(f"sugar: {modifiers['sugar_level']}")
            if modifiers.get("ice_level"):
                mod_parts.append(f"ice: {modifiers['ice_level']}")
            if modifiers.get("size"):
                mod_parts.append(f"size: {modifiers['size']}")
            if mod_parts:
                print(f"  │   ({', '.join(mod_parts)})")

        tags = item.get("food_tags") or []
        if tags:
            print(f"  │   [{', '.join(tags)}]")

    print(f"  │{'─' * 45}│")

    if receipt.get("discount"):
        disc = _fmt_currency(receipt["discount"], currency)
        print(f"  │ {'Discount':<32} {'-' + disc:>10} │")
    if receipt.get("tax_amount"):
        tax = _fmt_currency(receipt["tax_amount"], currency)
        print(f"  │ {'Tax':<32} {tax:>10} │")

    total_str = _fmt_currency(total, currency)
    print(f"  │ {'TOTAL':<32} {total_str:>10} │")
    print(f"  └{'─' * 45}┘")
    print()


def _save_receipt(receipt: dict) -> Path:
    """Write the finalized receipt as a JSON file."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = _datetime.now().strftime("%Y%m%d_%H%M%S")
    merchant_name = (receipt.get("merchant") or {}).get("name", "unknown")
    slug = "".join(c if c.isalnum() else "_" for c in merchant_name)[:30]
    filename = f"{timestamp}_{slug}.json"
    filepath = RECEIPTS_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    return filepath


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@function_tool
async def ask_user(
    ctx: RunContextWrapper[ReceiptParserContext],
    question: str,
    options: list[str],
    allow_skip: bool = True,
    field: Literal[
        "total", "date", "merchant", "category", "line_item", "edit_selection"
    ] | None = None,
) -> str:
    """Ask one clarification question and return the user's typed answer.

    Displays the question with numbered options, then waits for input.
    The answer is returned as the tool result so the agent can continue
    in the same turn.
    """
    print(f"\n  Bot: {question}")
    for i, opt in enumerate(options, 1):
        print(f"    [{i}] {opt}")
    if allow_skip and not any("skip" in o.lower() for o in options):
        print("    [0] Skip")

    answer = (await asyncio.to_thread(input, "  You: ")).strip()
    return answer or "skip"


@function_tool
async def submit_receipt_draft(
    ctx: RunContextWrapper[ReceiptParserContext],
    receipt: ReceiptData,
) -> str:
    """Submit the parsed receipt as a draft for user review.

    Assigns sequential [id] numbers to items, stores the draft in context,
    and displays the receipt card. The user will then confirm, edit, or
    describe changes.
    """
    raw = receipt.model_dump()
    for i, item in enumerate(raw.get("items", []), start=1):
        item["id"] = i
    ctx.context.draft = raw
    display_receipt_card(raw, "draft")
    print("  Type 'confirm' to save, or describe any changes.")
    return "Receipt card shown to user. Waiting for user response."


@function_tool
async def submit_receipt_final(
    ctx: RunContextWrapper[ReceiptParserContext],
) -> str:
    """Save the current draft receipt to disk.

    Reads the stored draft from context — no receipt data needed.
    Call this only after the user has confirmed the draft.
    """
    draft = ctx.context.draft
    if draft is None:
        return "Error: no draft receipt to save. Call submit_receipt_draft first."
    filepath = _save_receipt(draft)
    display_receipt_card(draft, "final")
    print(f"  ✅ Saved → {filepath}")
    ctx.context.draft = None
    return f"Receipt saved to {filepath}"


@function_tool
async def update_receipt(
    ctx: RunContextWrapper[ReceiptParserContext],
    patch: ReceiptPatch,
) -> str:
    """Patch the current draft receipt with only the changed fields.

    Items are matched by their [id] shown in the receipt card.
    Only include items that need updating. Re-displays the updated card.
    """
    draft = ctx.context.draft
    if draft is None:
        return "Error: no draft receipt to update. Call submit_receipt_draft first."

    updated = dict(draft)
    patch_dict = patch.model_dump(exclude_none=True)

    for key, value in patch_dict.items():
        if key == "merchant":
            updated["merchant"] = {**(updated.get("merchant") or {}), **value}
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

    ctx.context.draft = updated
    display_receipt_card(updated, "draft")
    print("  Receipt updated. Type 'confirm' to save, or describe more changes.")
    return "Receipt updated and shown to user."
