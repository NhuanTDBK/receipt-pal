"""BotManager — mirrors hackernews_digest bot.py pattern."""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from app.config import settings
from app.database import async_session_factory

logger = logging.getLogger(__name__)


def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context compatible with Docker Desktop for macOS.

    Docker Desktop's bridge networking can truncate SSL records mid-handshake,
    causing OpenSSL 3.x to raise UNEXPECTED_EOF_WHILE_READING. Setting
    OP_IGNORE_UNEXPECTED_EOF suppresses this and lets the connection proceed.
    """
    ctx = ssl.create_default_context()
    try:
        ctx.options |= ssl.OP_IGNORE_UNEXPECTED_EOF  # Python 3.11.4+ / OpenSSL 3.0.7+
    except AttributeError:
        pass
    return ctx


class IPv4AiohttpSession(AiohttpSession):
    """Force IPv4 + Docker-compatible SSL for Telegram API calls."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ssl_ctx = _build_ssl_context()
        self._connector_init["family"] = socket.AF_INET
        self._connector_init["ssl"] = ssl_ctx


class DatabaseMiddleware:
    """Inject an AsyncSession into every handler via data["session"]."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        async with async_session_factory() as session:
            data["session"] = session
            return await handler(event, data)


class BotManager:
    def __init__(self) -> None:
        self._bot: Bot | None = None
        self._dp: Dispatcher | None = None

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            raise RuntimeError("BotManager not initialized. Call initialize() first.")
        return self._bot

    @property
    def dispatcher(self) -> Dispatcher:
        if self._dp is None:
            raise RuntimeError("BotManager not initialized. Call initialize() first.")
        return self._dp

    async def initialize(self) -> None:
        storage = await self._build_storage()
        session = IPv4AiohttpSession() if settings.telegram_force_ipv4 else None
        self._bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            session=session,
        )
        self._dp = Dispatcher(storage=storage)
        self._setup_middleware()
        self._setup_handlers()
        logger.info("BotManager initialized")

    async def _build_storage(self) -> BaseStorage:
        if settings.redis_url:
            try:
                from aiogram.fsm.storage.redis import RedisStorage

                return RedisStorage.from_url(settings.redis_url)
            except Exception as exc:
                logger.warning("Redis unavailable, falling back to MemoryStorage: %s", exc)
        return MemoryStorage()

    def _setup_middleware(self) -> None:
        db_mw = DatabaseMiddleware()
        self._dp.message.middleware(db_mw)
        self._dp.callback_query.middleware(db_mw)
        self._dp.callback_query.middleware(CallbackAnswerMiddleware())

    def _setup_handlers(self) -> None:
        from app.presentation.bot.handlers.callbacks import router as callbacks_router
        from app.presentation.bot.handlers.commands import router as commands_router
        from app.presentation.bot.handlers.document import router as document_router
        from app.presentation.bot.handlers.photo import router as photo_router

        # Order matters: specific state/callback handlers first, fallback text last.
        self._dp.include_router(callbacks_router)
        self._dp.include_router(photo_router)
        self._dp.include_router(document_router)
        self._dp.include_router(commands_router)  # fallback_text is here (StateFilter(None))

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup=None,
        parse_mode: str | None = None,
    ) -> dict:
        """Send a message with automatic retry on rate-limit and network errors.

        Args:
            chat_id: Telegram chat ID.
            text: Message text.
            reply_markup: Optional inline keyboard markup.
            parse_mode: Parse mode override (defaults to HTML).

        Returns:
            Dict with ``message_id``, ``chat_id``, and ``date``.

        Raises:
            Exception: Re-raised after exhausting retry attempts.
        """
        max_attempts = max(1, settings.telegram_network_retry_attempts)
        base_delay = max(0.1, settings.telegram_network_retry_base_delay)

        for attempt in range(1, max_attempts + 1):
            try:
                message = await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode or ParseMode.HTML,
                )
                logger.debug("Sent message to %s: msg_id=%s", chat_id, message.message_id)
                return {
                    "message_id": message.message_id,
                    "chat_id": message.chat.id,
                    "date": message.date.isoformat(),
                }

            except TelegramRetryAfter as exc:
                if attempt >= max_attempts:
                    logger.error(
                        "Rate limited sending to %s after %d attempts: %s",
                        chat_id, attempt, exc,
                    )
                    raise
                delay = max(float(exc.retry_after), base_delay)
                logger.warning(
                    "Rate limited sending to %s; retrying in %.1fs (attempt %d/%d)",
                    chat_id, delay, attempt, max_attempts,
                )
                await asyncio.sleep(delay)

            except TelegramNetworkError as exc:
                if attempt >= max_attempts:
                    logger.error(
                        "Network error sending to %s after %d attempts: %s",
                        chat_id, attempt, exc,
                    )
                    raise
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Network error sending to %s; retrying in %.1fs (attempt %d/%d): %s",
                    chat_id, delay, attempt, max_attempts, exc,
                )
                await asyncio.sleep(delay)

            except Exception:
                logger.error("Error sending message to %s", chat_id, exc_info=True)
                raise

    async def start_polling(self) -> None:
        restart_delay = max(1.0, settings.telegram_polling_restart_delay)
        logger.info("Starting polling...")
        while True:
            try:
                await self._dp.start_polling(
                    self._bot, allowed_updates=["message", "callback_query"]
                )
                return
            except asyncio.CancelledError:
                raise
            except TelegramNetworkError as exc:
                logger.warning(
                    "Polling interrupted by network error, restarting in %.1fs: %s",
                    restart_delay, exc,
                )
                await asyncio.sleep(restart_delay)

    async def shutdown(self) -> None:
        if self._bot:
            await self._bot.session.close()
            logger.info("Bot session closed")

    async def stop(self) -> None:
        """Alias for shutdown() for backwards compatibility."""
        await self.shutdown()


_bot_manager: BotManager | None = None


def get_bot_manager() -> BotManager:
    global _bot_manager
    if _bot_manager is None:
        _bot_manager = BotManager()
    return _bot_manager


def set_bot_manager(manager: BotManager) -> None:
    """Set the global bot manager instance (useful for testing)."""
    global _bot_manager
    _bot_manager = manager


async def initialize_bot() -> BotManager:
    """Initialize the global bot manager (for use in startup hooks)."""
    manager = get_bot_manager()
    await manager.initialize()
    return manager


async def shutdown_bot() -> None:
    """Shutdown the global bot manager (for use in shutdown hooks)."""
    manager = get_bot_manager()
    await manager.shutdown()

