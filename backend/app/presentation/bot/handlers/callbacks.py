"""Callback handlers for receipt confirm/edit/cancel and AskUser responses."""

from __future__ import annotations

import logging
import uuid

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.presentation.bot.formatters.receipt_formatter import format_receipt_card
from app.presentation.bot.states import ReceiptFlow
from app.repositories import receipt_repo
from app.services.agent_runner import run_agent

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


@router.callback_query(F.data == "receipt:confirm")
async def callback_confirm(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Save the draft receipt to DB. Deterministic — no agent invocation."""
    data = await state.get_data()
    draft = data.get("draft")
    conversation_id = data.get("conversation_id")
    user_id = data.get("user_id")

    if not draft or not user_id:
        await callback.message.edit_text("⚠️ No draft to save. Please send a photo.")
        await state.clear()
        return

    await receipt_repo.save_receipt(
        session,
        user_id=uuid.UUID(user_id),
        conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
        data=draft,
    )
    await session.commit()

    card_text = format_receipt_card(draft, is_draft=False)
    await callback.message.edit_text(card_text + "\n\n✅ Saved!")
    await state.clear()


@router.callback_query(F.data == "receipt:edit")
async def callback_edit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft = data.get("draft", {})
    if not draft:
        await callback.message.answer("⚠️ No active draft to edit.")
        return

    await state.set_state(ReceiptFlow.EDITING_FIELD)
    await callback.message.answer(
        '✏️ Describe what to change (e.g. "merchant is Starbucks" or "total is 55000"):'
    )


@router.callback_query(F.data == "receipt:cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text("❌ Receipt discarded.")
    await state.clear()


@router.callback_query(F.data.startswith("ask:"))
async def callback_ask_user(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    """Handle a user selecting an AskUser option — feeds answer into the agent."""
    parts = callback.data.split(":", 2)
    selected_text = parts[2] if len(parts) > 2 else "skip"

    await callback.message.edit_reply_markup(reply_markup=None)

    status_msg = await callback.message.answer(
        f"You selected: <b>{selected_text}</b>\n\n🔄 Processing..."
    )

    await run_agent(
        bot,
        callback.message,
        status_msg,
        session,
        state,
        user_input=selected_text,
    )


@router.message(ReceiptFlow.EDITING_FIELD)
async def handle_edit_input(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    """User typed a correction while in EDITING_FIELD state — feeds into the agent."""
    data = await state.get_data()
    draft = data.get("draft", {})

    if not draft:
        await message.answer("⚠️ No active draft. Please send a photo.")
        await state.clear()
        return

    status_msg = await message.answer("🔄 Updating receipt...")

    await run_agent(
        bot,
        message,
        status_msg,
        session,
        state,
        user_input=message.text,
    )
