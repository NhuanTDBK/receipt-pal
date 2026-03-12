"""HTML receipt card formatter for Telegram messages."""

from __future__ import annotations


def format_vnd(amount: int) -> str:
    return f"{amount:,}đ".replace(",", ".")


def format_currency(amount: int, currency: str = "VND") -> str:
    if currency == "VND":
        return format_vnd(amount)
    return f"{amount:,} {currency}"


CONFIDENCE_EMOJI = {"high": "🟢", "medium": "🟡", "low": "🔴"}

CATEGORY_EMOJI = {
    "dining": "🍽",
    "cafe": "☕",
    "grocery": "🛒",
    "convenience": "🏪",
    "health": "💊",
    "entertainment": "🎬",
    "transport": "🚗",
    "utilities": "💡",
    "rent": "🏠",
    "other": "📦",
}

SOURCE_LABEL = {
    "paper": "paper",
    "shopeefood": "ShopeeFood",
    "grabfood": "GrabFood",
    "gofood": "GoFood",
    "baemin": "Baemin",
    "app_unknown": "delivery app",
}


def format_receipt_card(receipt: dict, is_draft: bool = True) -> str:
    """Format a receipt dict as an HTML Telegram message."""
    merchant = receipt.get("merchant", {})
    name = merchant.get("name", "Unknown")
    address = merchant.get("address", "")
    dt = receipt.get("datetime", "")
    category = receipt.get("category", "other")
    source = receipt.get("source", "paper")
    currency = receipt.get("currency", "VND")
    total = receipt.get("total", 0)

    cat_icon = CATEGORY_EMOJI.get(category, "📦")
    src_label = SOURCE_LABEL.get(source, source)
    status = "🧾 DRAFT" if is_draft else "✅ CONFIRMED"

    lines: list[str] = [
        f"<b>{status}</b>",
        f"🏪 <b>{_esc(name)}</b>",
    ]
    if address:
        lines.append(f"📍 {_esc(address)}")
    if dt:
        lines.append(f"🕐 {_esc(dt)}")
    lines.append(f"{cat_icon} {category} · {src_label}")
    lines.append("")
    lines.append("<b>Items:</b>")

    for item in receipt.get("items", []):
        item_id = item.get("id", "")
        item_name = item.get("name", "?")
        qty = item.get("quantity", 1)
        amount = item.get("amount", 0)
        confidence = item.get("confidence", "high")
        conf_icon = CONFIDENCE_EMOJI.get(confidence, "")

        qty_str = f"{qty}× " if qty > 1 else ""
        id_str = f"[{item_id}] " if item_id != "" else ""
        amount_str = format_currency(amount, currency)
        lines.append(f"  {id_str}{qty_str}<i>{_esc(item_name)}</i> — {amount_str} {conf_icon}")

        for topping in item.get("toppings") or []:
            tp_name = topping.get("name", "")
            tp_price = topping.get("price", 0)
            price_str = f"+{format_currency(tp_price, currency)}" if tp_price else "free"
            lines.append(f"    + {_esc(tp_name)} ({price_str})")

        modifiers = item.get("modifiers") or {}
        mod_parts = []
        if modifiers.get("sugar_level"):
            mod_parts.append(f"sugar: {modifiers['sugar_level']}")
        if modifiers.get("ice_level"):
            mod_parts.append(f"ice: {modifiers['ice_level']}")
        if modifiers.get("size"):
            mod_parts.append(f"size: {modifiers['size']}")
        if mod_parts:
            lines.append(f"    ({', '.join(mod_parts)})")

        tags = item.get("food_tags") or []
        if tags:
            lines.append(f"    <code>[{', '.join(tags)}]</code>")

    lines.append("")

    if receipt.get("subtotal") and receipt["subtotal"] != total:
        lines.append(f"Subtotal: {format_currency(receipt['subtotal'], currency)}")
    if receipt.get("discount"):
        lines.append(f"Discount: -{format_currency(receipt['discount'], currency)}")
    if receipt.get("tax_amount"):
        lines.append(f"Tax: {format_currency(receipt['tax_amount'], currency)}")

    lines.append(f"💰 Total: <b>{format_currency(total, currency)}</b>")

    if receipt.get("notes"):
        lines.append(f"\n📝 {_esc(receipt['notes'])}")

    return "\n".join(lines)


def format_history_item(receipt: dict, index: int) -> str:
    """Short one-line summary for the /history command."""
    merchant = receipt.get("merchant_name", "Unknown")
    total = receipt.get("total", 0)
    currency = receipt.get("currency", "VND")
    dt = receipt.get("receipt_datetime", "")
    cat = receipt.get("category", "other")
    cat_icon = CATEGORY_EMOJI.get(cat, "📦")
    date_str = dt.strftime("%d/%m/%Y") if hasattr(dt, "strftime") else str(dt)[:10]
    return f"{index}. {cat_icon} <b>{_esc(merchant)}</b> — {format_currency(total, currency)} ({date_str})"


def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
