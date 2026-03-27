"""SubmitReceipt tools — draft display and final save."""

from __future__ import annotations

from typing import Literal

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel

from app.presentation.bot.formatters.receipt_formatter import format_receipt_card
from app.presentation.bot.keyboards.receipt import receipt_review_keyboard
from app.presentation.bot.states import ReceiptFlow
from app.repositories import receipt_repo
from app.services.agent_context import TelegramAgentContext

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
            "sugary",
            "fried",
            "healthy",
            "alcohol",
            "caffeine",
            "dairy",
            "spicy",
            "non_food",
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
    category: (
        Literal[
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
        ]
        | None
    ) = None
    source: Literal[
        "paper",
        "shopeefood",
        "grabfood",
        "gofood",
        "baemin",
        "app_unknown",
    ] = "paper"


def _assign_item_ids(receipt: dict) -> dict:
    """Assign sequential integer IDs to items for patch matching."""
    receipt = dict(receipt)
    for i, item in enumerate(receipt.get("items", []), start=1):
        item["id"] = i
    return receipt


@function_tool
async def submit_receipt_draft(
    ctx: RunContextWrapper[TelegramAgentContext],
    receipt: ReceiptData,
) -> str:
    """Submit the parsed receipt as a draft for user review.

    Assigns sequential [id] numbers to items, stores the draft in context,
    and displays the receipt card. The user will then confirm, edit, or cancel.
    """
    tc = ctx.context
    tc.suppress_final_text = True
    raw = _assign_item_ids(receipt.model_dump())
    tc.draft = raw

    card_text = format_receipt_card(raw, is_draft=True)

    await tc.state.set_state(ReceiptFlow.REVIEWING)
    await tc.state.update_data(
        draft=raw,
        conversation_id=str(tc.conversation_id),
        user_id=str(tc.user_id),
    )
    await tc.status_msg.edit_text(card_text, reply_markup=receipt_review_keyboard())
    return "Receipt card shown to user with confirm/edit/cancel options."


@function_tool
async def submit_receipt_final(
    ctx: RunContextWrapper[TelegramAgentContext],
) -> str:
    """Save the confirmed receipt to the database.

    Reads the stored draft from FSM state. Call only after user confirms.
    """
    tc = ctx.context
    data = await tc.state.get_data()
    draft = data.get("draft")

    if not draft:
        return "Error: no draft receipt to save. Call submit_receipt_draft first."

    receipt = await receipt_repo.save_receipt(
        tc.db_session,
        user_id=tc.user_id,
        conversation_id=tc.conversation_id,
        data=draft,
    )
    await tc.db_session.commit()

    card_text = format_receipt_card(draft, is_draft=False)
    await tc.status_msg.edit_text(card_text + "\n\n✅ Saved!")
    await tc.state.clear()

    return f"Receipt saved (id={receipt.id})."
