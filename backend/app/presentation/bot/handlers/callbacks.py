"""Callback handlers for receipt confirm/edit/cancel and AskUser responses."""

from __future__ import annotations

import logging
import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.presentation.bot.formatters.receipt_formatter import format_receipt_card
from app.presentation.bot.keyboards.receipt import ask_user_keyboard, receipt_review_keyboard
from app.presentation.bot.states import ReceiptFlow
from app.repositories import conversation_repo, receipt_repo
from app.services.receipt_parser import apply_update_patch

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


@router.callback_query(F.data == "receipt:confirm")
async def callback_confirm(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    data = await state.get_data()
    draft = data.get("draft")
    conversation_id = data.get("conversation_id")
    user_id = data.get("user_id")

    if not draft or not user_id:
        await callback.message.edit_text("⚠️ No draft to save. Please send a photo.")
        await state.clear()
        return

    receipt = await receipt_repo.save_receipt(
        session,
        user_id=uuid.UUID(user_id),
        conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
        data=draft,
    )

    if conversation_id:
        await conversation_repo.append_message(
            session,
            conversation_id=uuid.UUID(conversation_id),
            role="user",
            content="confirm",
        )
        await conversation_repo.append_message(
            session,
            conversation_id=uuid.UUID(conversation_id),
            role="assistant",
            content=f"Receipt saved (id={receipt.id}).",
        )
        await session.commit()

    card_text = format_receipt_card(draft, is_draft=False)
    await callback.message.edit_text(card_text + "\n\n✅ Saved!")
    await state.clear()


@router.callback_query(F.data == "receipt:edit")
async def callback_edit(
    callback: CallbackQuery, state: FSMContext
) -> None:
    data = await state.get_data()
    draft = data.get("draft", {})
    if not draft:
        await callback.message.answer("⚠️ No active draft to edit.")
        return

    await state.set_state(ReceiptFlow.EDITING_FIELD)
    await callback.message.answer(
        "✏️ Describe what to change (e.g. \"merchant is Starbucks\" or \"total is 55000\"):"
    )


@router.callback_query(F.data == "receipt:cancel")
async def callback_cancel(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    data = await state.get_data()
    conversation_id = data.get("conversation_id")

    if conversation_id:
        await conversation_repo.append_message(
            session,
            conversation_id=uuid.UUID(conversation_id),
            role="user",
            content="cancel",
        )
        await session.commit()

    await callback.message.edit_text("❌ Receipt discarded.")
    await state.clear()


@router.callback_query(F.data.startswith("ask:"))
async def callback_ask_user(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Handle a user selecting an AskUser option."""
    parts = callback.data.split(":", 2)
    selected_text = parts[2] if len(parts) > 2 else "skip"

    data = await state.get_data()
    conversation_id = data.get("conversation_id")

    if conversation_id:
        await conversation_repo.append_message(
            session,
            conversation_id=uuid.UUID(conversation_id),
            role="user",
            content=selected_text,
        )
        await session.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"You selected: <b>{selected_text}</b>")


@router.message(ReceiptFlow.EDITING_FIELD)
async def handle_edit_input(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """User typed a correction while in EDITING_FIELD state."""
    from app.presentation.bot.handlers.photo import _get_or_download_image
    from app.services.receipt_parser import ReceiptParser

    data = await state.get_data()
    draft = data.get("draft", {})
    conversation_id = data.get("conversation_id")
    user_id = data.get("user_id")

    if not draft:
        await message.answer("⚠️ No active draft. Please send a photo.")
        await state.clear()
        return

    if conversation_id:
        await conversation_repo.append_message(
            session,
            conversation_id=uuid.UUID(conversation_id),
            role="user",
            content=message.text,
        )
        await session.commit()

    history_msgs = await conversation_repo.load_history(session, uuid.UUID(conversation_id))
    from app.presentation.bot.handlers.photo import _build_gemini_history

    history = _build_gemini_history(history_msgs[:-1])

    status_msg = await message.answer("🔄 Updating receipt...")
    parser = ReceiptParser()

    async def on_tool_call(tool_name: str, args: dict) -> str:
        nonlocal draft
        if tool_name == "UpdateReceipt":
            draft = apply_update_patch(draft, args)
            await state.update_data(draft=draft)

            if conversation_id:
                await conversation_repo.append_message(
                    session,
                    conversation_id=uuid.UUID(conversation_id),
                    role="assistant",
                    tool_name="UpdateReceipt",
                    tool_args=args,
                )
                await session.commit()

            card_text = format_receipt_card(draft, is_draft=True)
            await state.set_state(ReceiptFlow.REVIEWING)
            await status_msg.edit_text(card_text, reply_markup=receipt_review_keyboard())
            return "Receipt updated and shown."

        elif tool_name == "SubmitReceipt" and args.get("mode") == "final":
            return "Final acknowledged."

        return f"Unhandled tool in edit mode: {tool_name}"

    try:
        _, usage = await parser.parse(
            images=[],
            history=history,
            new_text=message.text,
            on_tool_call=on_tool_call,
            session_id=conversation_id,  # str(conversation.id) → Langfuse session_id + DB key
            user_id=user_id,             # str(db_user.id)       → Langfuse user_id
        )
        if conversation_id:
            await conversation_repo.add_token_usage(
                session,
                conversation_id=uuid.UUID(conversation_id),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
            await session.commit()
    except Exception as exc:
        logger.exception("Edit parse error: %s", exc)
        await status_msg.edit_text("⚠️ Could not apply the edit. Please try again.")
