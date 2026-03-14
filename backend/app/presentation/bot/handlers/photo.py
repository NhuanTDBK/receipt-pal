"""Photo handler — core receipt parsing flow with multi-image and conversation support."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.presentation.bot.formatters.receipt_formatter import format_receipt_card
from app.presentation.bot.keyboards.receipt import ask_user_keyboard, receipt_review_keyboard
from app.presentation.bot.states import ReceiptFlow
from app.repositories import conversation_repo, user_repo
from app.services.photo_store import PhotoStore
from app.services.receipt_parser import ReceiptParser, TokenUsage, assign_item_ids

logger = logging.getLogger(__name__)
router = Router(name="photo")

# Seconds to wait before processing a media group (album) to collect all photos
MEDIA_GROUP_WAIT = 1.5

# In-memory buffer for media group collection: {media_group_id: [file_ids]}
_media_group_buffer: dict[str, list[str]] = {}
_media_group_locks: dict[str, asyncio.Lock] = {}
_media_group_tasks: dict[str, asyncio.Task] = {}


async def _get_or_download_image(bot: Bot, file_id: str) -> bytes | None:
    photo_store = PhotoStore.get_instance()
    cached = photo_store.get(file_id)
    if cached:
        return cached
    try:
        file = await bot.get_file(file_id)
        image_bytes = await bot.download_file(file.file_path)
        data = image_bytes.read() if hasattr(image_bytes, "read") else bytes(image_bytes)
        photo_store.store(file_id, data)
        return data
    except Exception as exc:
        logger.error("Failed to download photo %s: %s", file_id, exc)
        return None


def _build_gemini_history(messages) -> list[dict]:
    """Convert ConversationMessage ORM objects to Gemini API message dicts."""
    result: list[dict] = []
    for msg in messages:
        entry: dict[str, Any] = {"role": msg.role}
        if msg.tool_name:
            entry["content"] = ""
            entry["tool_calls"] = [
                {
                    "id": f"call_{msg.id}",
                    "type": "function",
                    "function": {"name": msg.tool_name, "arguments": str(msg.tool_args or {})},
                }
            ]
        elif msg.role == "tool":
            entry["role"] = "tool"
            entry["tool_call_id"] = f"call_{msg.id}"
            entry["content"] = msg.content or ""
        else:
            entry["content"] = msg.content or ""
        result.append(entry)
    return result


async def _process_receipt(
    message: Message,
    file_ids: list[str],
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    *,
    is_pdf: bool = False,
) -> None:
    """Core logic: download receipt media, call parser, handle tool results.

    Works for both photo receipts (is_pdf=False) and PDF receipts (is_pdf=True).
    file_ids are Telegram file IDs; bytes are cached in PhotoStore by file_id.
    """
    media_label = "PDF receipt" if is_pdf else "receipt photo"
    user_text = f"Here is a {media_label}. Please parse it."

    user = message.from_user
    db_user = await user_repo.get_or_create_user(
        session,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "Friend",
    )

    conversation = await conversation_repo.get_active_conversation(session, db_user.id)

    await conversation_repo.append_message(
        session,
        conversation_id=conversation.id,
        role="user",
        content=user_text,
        image_file_ids=file_ids,
    )
    await session.commit()

    history_msgs = await conversation_repo.load_history(session, conversation.id)
    history = _build_gemini_history(history_msgs[:-1])

    media_bytes: list[bytes] = []
    for fid in file_ids:
        data = await _get_or_download_image(bot, fid)
        if data:
            media_bytes.append(data)

    if not media_bytes:
        label = "PDF" if is_pdf else "photo"
        await message.answer(f"⚠️ Could not download the {label}. Please try again.")
        return

    status_msg = await message.answer(
        "🔍 Parsing your PDF receipt…" if is_pdf else "🔍 Parsing your receipt..."
    )

    parser = ReceiptParser()
    state_data = await state.get_data()
    ask_sent = False

    async def on_tool_call(tool_name: str, args: dict) -> str:
        nonlocal ask_sent

        if tool_name == "AskUser":
            question = args.get("question", "")
            options = args.get("options", [])
            allow_skip = args.get("allow_skip", True)

            await conversation_repo.append_message(
                session,
                conversation_id=conversation.id,
                role="assistant",
                tool_name="AskUser",
                tool_args=args,
            )
            await session.commit()

            await status_msg.edit_text(
                f"❓ {question}",
                reply_markup=ask_user_keyboard(options, allow_skip),
            )
            ask_sent = True
            return "Question shown to user. Awaiting their answer."

        elif tool_name == "SubmitReceipt":
            mode = args.get("mode", "draft")

            await conversation_repo.append_message(
                session,
                conversation_id=conversation.id,
                role="assistant",
                tool_name="SubmitReceipt",
                tool_args=args,
            )
            await session.commit()

            if mode == "draft":
                receipt = assign_item_ids(args)
                card_text = format_receipt_card(receipt, is_draft=True)
                await state.set_state(ReceiptFlow.REVIEWING)
                await state.update_data(
                    draft=receipt,
                    conversation_id=str(conversation.id),
                    user_id=str(db_user.id),
                )
                await status_msg.edit_text(card_text, reply_markup=receipt_review_keyboard())
                return "Receipt card shown to user with confirm/edit/cancel options."

            elif mode == "final":
                return "Final mode acknowledged."

        elif tool_name == "UpdateReceipt":
            from app.services.receipt_parser import apply_update_patch

            current = state_data.get("draft", {})
            updated = apply_update_patch(current, args)
            card_text = format_receipt_card(updated, is_draft=True)

            await conversation_repo.append_message(
                session,
                conversation_id=conversation.id,
                role="assistant",
                tool_name="UpdateReceipt",
                tool_args=args,
            )
            await session.commit()

            await state.update_data(draft=updated)
            await status_msg.edit_text(card_text, reply_markup=receipt_review_keyboard())
            return "Receipt updated and shown to user."

        return f"Unknown tool: {tool_name}"

    parse_kwargs: dict = dict(
        history=history,
        new_text=user_text,
        on_tool_call=on_tool_call,
        session_id=str(conversation.id),
        user_id=str(db_user.id),
    )
    if is_pdf:
        parse_kwargs["images"] = []
        parse_kwargs["pdfs"] = media_bytes
    else:
        parse_kwargs["images"] = media_bytes

    try:
        _, usage = await parser.parse(**parse_kwargs)
        await conversation_repo.add_token_usage(
            session,
            conversation_id=conversation.id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        await session.commit()
    except Exception as exc:
        logger.exception("Parser error: %s", exc)
        await status_msg.edit_text("⚠️ Failed to parse the receipt. Please try again.")
        await state.clear()


@router.message(F.photo)
async def handle_photo(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    photo = message.photo[-1]  # highest resolution

    if message.media_group_id:
        group_id = message.media_group_id

        if group_id not in _media_group_buffer:
            _media_group_buffer[group_id] = []
            _media_group_locks[group_id] = asyncio.Lock()

        async with _media_group_locks[group_id]:
            _media_group_buffer[group_id].append(photo.file_id)

        if group_id in _media_group_tasks:
            _media_group_tasks[group_id].cancel()

        async def process_group():
            await asyncio.sleep(MEDIA_GROUP_WAIT)
            file_ids = _media_group_buffer.pop(group_id, [])
            _media_group_locks.pop(group_id, None)
            _media_group_tasks.pop(group_id, None)
            if file_ids:
                try:
                    await _process_receipt(message, file_ids, session, state, bot)
                except Exception as exc:
                    logger.exception("Unhandled error processing media group %s: %s", group_id, exc)
                    from app.presentation.bot.bot import get_bot_manager
                    try:
                        await get_bot_manager().send_message(
                            chat_id=message.chat.id,
                            text="⚠️ Failed to process your photos. Please try again.",
                        )
                    except Exception:
                        logger.error("Failed to send error notification to %s", message.chat.id)

        task = asyncio.create_task(process_group())
        _media_group_tasks[group_id] = task
    else:
        await _process_receipt(message, [photo.file_id], session, state, bot)
