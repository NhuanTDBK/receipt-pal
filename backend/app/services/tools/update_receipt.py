"""UpdateReceipt tool — patches the current draft and re-displays."""

from __future__ import annotations

from typing import Literal

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel

from app.presentation.bot.formatters.receipt_formatter import format_receipt_card
from app.presentation.bot.keyboards.receipt import receipt_review_keyboard
from app.presentation.bot.states import ReceiptFlow
from app.services.agent_context import TelegramAgentContext
from app.services.tools.submit_receipt import ItemModifiers, ItemTopping, MerchantInfo


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
    currency: str | None = None
    subtotal: int | None = None
    discount: int | None = None
    tax_rate: float | None = None
    tax_amount: int | None = None
    total: int | None = None
    notes: str | None = None
    items: list[ItemPatch] | None = None


def _apply_patch(current: dict, patch: dict) -> dict:
    """Merge a patch into the current draft receipt."""
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


@function_tool
async def update_receipt(
    ctx: RunContextWrapper[TelegramAgentContext],
    patch: ReceiptPatch,
) -> str:
    """Patch the current draft receipt with only the changed fields.

    Items are matched by their [id] shown in the receipt card.
    Only include items that need updating. Re-displays the updated card.
    """
    tc = ctx.context
    data = await tc.state.get_data()
    draft = data.get("draft")

    if not draft:
        return "Error: no draft receipt to update. Call submit_receipt_draft first."

    updated = _apply_patch(draft, patch.model_dump(exclude_none=True))
    tc.draft = updated

    await tc.state.set_state(ReceiptFlow.REVIEWING)
    await tc.state.update_data(draft=updated)

    card_text = format_receipt_card(updated, is_draft=True)
    await tc.status_msg.edit_text(card_text, reply_markup=receipt_review_keyboard())
    return "Receipt updated and shown to user."
