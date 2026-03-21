"""Photo handler — receipt parsing flow with multi-image support."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_runner import run_agent
from app.services.photo_store import PhotoStore

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
        data = (
            image_bytes.read() if hasattr(image_bytes, "read") else bytes(image_bytes)
        )
        photo_store.store(file_id, data)
        return data
    except Exception as exc:
        logger.error("Failed to download photo %s: %s", file_id, exc)
        return None


async def _process_receipt(
    message: Message,
    file_ids: list[str],
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    *,
    is_pdf: bool = False,
) -> None:
    """Core logic: download receipt media, run agent."""
    media_label = "PDF receipt" if is_pdf else "receipt photo"
    user_text = f"Here is a {media_label}. Please parse it."

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

    if is_pdf:
        await run_agent(
            bot,
            message,
            status_msg,
            session,
            state,
            user_text,
            pdfs=media_bytes,
        )
    else:
        await run_agent(
            bot,
            message,
            status_msg,
            session,
            state,
            user_text,
            images=media_bytes,
        )


@router.message(F.photo)
async def handle_photo(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
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
                    logger.exception(
                        "Unhandled error processing media group %s: %s",
                        group_id,
                        exc,
                    )
                    from app.presentation.bot.bot import get_bot_manager

                    try:
                        await get_bot_manager().send_message(
                            chat_id=message.chat.id,
                            text="⚠️ Failed to process your photos. Please try again.",
                        )
                    except Exception:
                        logger.error(
                            "Failed to send error notification to %s",
                            message.chat.id,
                        )

        task = asyncio.create_task(process_group())
        _media_group_tasks[group_id] = task
    else:
        await _process_receipt(message, [photo.file_id], session, state, bot)
