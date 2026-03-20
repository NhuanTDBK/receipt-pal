"""Typed context passed to all agent tools during a Telegram interaction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.fsm.context import FSMContext
    from aiogram.types import Message
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class TelegramAgentContext:
    """Carries Telegram handles and mutable state across tool calls within one run."""

    bot: Bot
    message: Message
    status_msg: Message
    state: FSMContext
    db_session: AsyncSession
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    draft: dict | None = None
