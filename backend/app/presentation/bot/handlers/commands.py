"""Command handlers: /start, /help, /history, /stats."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.presentation.bot.formatters.receipt_formatter import (
    CATEGORY_EMOJI,
    format_currency,
    format_history_item,
)
from app.repositories import conversation_repo, receipt_repo, user_repo

router = Router(name="commands")

WELCOME_MESSAGE = (
    "👋 Welcome to <b>Receipt Pal</b>!\n\n"
    "Send me a photo (or multiple photos) of your receipt and I'll parse it for you.\n\n"
    "<b>Commands:</b>\n"
    "/history — your last 10 receipts\n"
    "/stats — spending by category\n"
    "/usage — token usage stats\n"
    "/help — show this message"
)

HELP_MESSAGE = (
    "<b>Receipt Pal — How to use</b>\n\n"
    "📸 <b>Parse a receipt:</b> Send one or more photos of the receipt.\n"
    "   Multiple photos = same receipt captured in parts.\n\n"
    "✅ <b>Confirm</b> the parsed card to save it.\n"
    "✏️ <b>Edit</b> to correct any field.\n"
    "❌ <b>Cancel</b> to discard.\n\n"
    "<b>Commands:</b>\n"
    "/history — last 10 saved receipts\n"
    "/stats — spending totals by category\n"
    "/usage — token usage stats\n"
    "/help — this message"
)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    await user_repo.get_or_create_user(
        session,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "Friend",
    )
    await message.answer(WELCOME_MESSAGE)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_MESSAGE)


@router.message(Command("history"))
async def cmd_history(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    db_user = await user_repo.get_or_create_user(
        session,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "Friend",
    )
    receipts = await receipt_repo.list_receipts(session, db_user.id, limit=10)

    if not receipts:
        await message.answer("No receipts yet. Send me a photo to get started! 📸")
        return

    lines = ["<b>Your last receipts:</b>\n"]
    for i, r in enumerate(receipts, start=1):
        lines.append(
            format_history_item(
                {
                    "merchant_name": r.merchant_name,
                    "total": r.total,
                    "currency": r.currency,
                    "category": r.category,
                    "receipt_datetime": r.receipt_datetime,
                },
                i,
            )
        )
    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    db_user = await user_repo.get_or_create_user(
        session,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "Friend",
    )
    stats = await receipt_repo.get_spending_stats(session, db_user.id)

    if not stats:
        await message.answer("No spending data yet. Save some receipts first! 📸")
        return

    lines = ["<b>Spending by category:</b>\n"]
    grand_total = sum(s["total"] for s in stats)
    for s in stats:
        cat = s["category"]
        icon = CATEGORY_EMOJI.get(cat, "📦")
        amount = format_currency(s["total"])
        pct = round(s["total"] / grand_total * 100) if grand_total else 0
        lines.append(f"{icon} {cat}: <b>{amount}</b> ({pct}%)")

    lines.append(f"\n💰 Grand total: <b>{format_currency(grand_total)}</b>")
    await message.answer("\n".join(lines))


@router.message(Command("usage"))
async def cmd_usage(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    db_user = await user_repo.get_or_create_user(
        session,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "Friend",
    )
    stats = await conversation_repo.get_usage_stats(session, db_user.id)

    if stats["total_tokens"] == 0:
        await message.answer("No token usage yet. Send a receipt photo to get started! 📸")
        return

    def fmt(n: int) -> str:
        return f"{n:,}"

    lines = [
        "📊 <b>Your token usage</b>\n",
        f"Input tokens:   <b>{fmt(stats['input_tokens'])}</b>",
        f"Output tokens:  <b>{fmt(stats['output_tokens'])}</b>",
        "─────────────────────",
        f"Total tokens:   <b>{fmt(stats['total_tokens'])}</b>",
        f"\nAcross <b>{stats['conversation_count']}</b> conversation(s)",
    ]
    await message.answer("\n".join(lines))
