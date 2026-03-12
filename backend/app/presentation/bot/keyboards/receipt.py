from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def receipt_review_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Confirm", callback_data="receipt:confirm"),
        InlineKeyboardButton(text="✏️ Edit", callback_data="receipt:edit"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="receipt:cancel"),
    )
    return builder.as_markup()


def ask_user_keyboard(options: list[str], allow_skip: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, option in enumerate(options):
        builder.button(text=option, callback_data=f"ask:{i}:{option[:50]}")
    if allow_skip and not any("skip" in o.lower() for o in options):
        builder.button(text="Skip", callback_data="ask:skip:skip")
    builder.adjust(2)
    return builder.as_markup()
