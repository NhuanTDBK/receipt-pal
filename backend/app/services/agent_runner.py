"""Agent runner service — orchestrates Runner.run() with Telegram context."""

from __future__ import annotations

import base64
import logging
import uuid

from agents import Runner
from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine
from app.repositories import conversation_repo, user_repo, user_settings_repo
from app.services.agent import build_receipt_agent, configure_provider
from app.services.agent_context import TelegramAgentContext

logger = logging.getLogger(__name__)

# One-time SDK configuration flag
_provider_configured = False


def _ensure_provider_configured() -> None:
    global _provider_configured
    if not _provider_configured:
        configure_provider()
        _provider_configured = True


def _encode_image(image_bytes: bytes) -> dict:
    """Encode image bytes as a base64 image_url content part."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
    }


def _encode_pdf(pdf_bytes: bytes) -> dict:
    """Encode PDF bytes as a base64 content part."""
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:application/pdf;base64,{b64}"},
    }


def _build_input(
    text: str | None,
    images: list[bytes] | None = None,
    pdfs: list[bytes] | None = None,
) -> str | list[dict]:
    """Build the input for Runner.run().

    Returns a simple string if text-only, or a list of content parts
    if media is included.
    """
    content_parts: list[dict] = []

    if text:
        content_parts.append({"type": "text", "text": text})

    for img in images or []:
        content_parts.append(_encode_image(img))

    for pdf in pdfs or []:
        content_parts.append(_encode_pdf(pdf))

    if not content_parts:
        return "."

    if len(content_parts) == 1 and content_parts[0].get("type") == "text":
        return content_parts[0]["text"]

    return content_parts


async def run_agent(
    bot: Bot,
    message: Message,
    status_msg: Message,
    db_session: AsyncSession,
    state: FSMContext,
    user_input: str | None,
    *,
    images: list[bytes] | None = None,
    pdfs: list[bytes] | None = None,
) -> None:
    """Run the receipt agent for a single Telegram interaction.

    Handles:
    - User resolution (get_or_create)
    - Conversation management (get_active)
    - Settings loading
    - Agent construction with settings-aware instructions
    - SQLAlchemySession for conversation persistence
    - Token usage tracking
    """
    _ensure_provider_configured()

    tg_user = message.from_user
    db_user = await user_repo.get_or_create_user(
        db_session,
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name or "Friend",
    )

    conversation = await conversation_repo.get_active_conversation(db_session, db_user.id)
    await db_session.commit()

    user_settings = await user_settings_repo.get_or_create_settings(db_session, db_user.id)

    agent = build_receipt_agent(user_settings)

    agent_session = SQLAlchemySession(
        str(conversation.id),
        engine=engine,
        create_tables=True,
    )

    context = TelegramAgentContext(
        bot=bot,
        message=message,
        status_msg=status_msg,
        state=state,
        db_session=db_session,
        user_id=db_user.id,
        conversation_id=conversation.id,
    )

    input_data = _build_input(user_input, images=images, pdfs=pdfs)

    try:
        result = await Runner.run(
            agent,
            input_data,
            context=context,
            session=agent_session,
        )

        # Track token usage
        if result.raw_responses:
            total_input = 0
            total_output = 0
            for resp in result.raw_responses:
                usage = getattr(resp, "usage", None)
                if usage:
                    total_input += getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
                    total_output += getattr(usage, "completion_tokens", 0) or getattr(usage, "output_tokens", 0) or 0

            if total_input or total_output:
                await conversation_repo.add_token_usage(
                    db_session,
                    conversation_id=conversation.id,
                    input_tokens=total_input,
                    output_tokens=total_output,
                )
                await db_session.commit()

        # If the agent produced text output (not just tool calls), send it
        if result.final_output and isinstance(result.final_output, str):
            text = result.final_output.strip()
            if text:
                await message.answer(text)

    except Exception as exc:
        logger.exception("Agent run error: %s", exc)
        await status_msg.edit_text("⚠️ Failed to process. Please try again.")
        await state.clear()
