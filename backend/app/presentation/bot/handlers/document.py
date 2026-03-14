"""Document handler — accepts PDF files as receipt input."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.presentation.bot.handlers.photo import _get_or_download_image, _process_receipt

logger = logging.getLogger(__name__)
router = Router(name="document")

PDF_MIME_TYPE = "application/pdf"
MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB — Telegram bot download limit


@router.message(F.document.mime_type == PDF_MIME_TYPE)
async def handle_pdf(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    """Parse a PDF receipt using the same Gemini pipeline as photo receipts."""
    doc = message.document

    if doc.file_size and doc.file_size > MAX_PDF_SIZE_BYTES:
        await message.reply(
            "That PDF is too large to process (max 20 MB). "
            "Try sending a compressed version."
        )
        return

    # Pre-download to verify the file is accessible before acknowledging
    pdf_bytes = await _get_or_download_image(bot, doc.file_id)
    if not pdf_bytes:
        await message.reply("⚠️ Could not download the PDF. Please try again.")
        return

    await _process_receipt(
        message,
        [doc.file_id],
        session,
        state,
        bot,
        is_pdf=True,
    )


@router.message(F.document)
async def handle_unsupported_document(message: Message) -> None:
    """Reject non-PDF document uploads with a helpful message."""
    await message.reply(
        "I can only process PDF files and photos. "
        "Please send your receipt as a PDF or a photo. 📸"
    )
