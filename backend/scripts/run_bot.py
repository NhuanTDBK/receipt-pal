"""Entry point for the Receipt Pal Telegram bot."""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure backend/ is on the Python path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def check_postgres() -> None:
    """Verify PostgreSQL is reachable before starting."""
    from sqlalchemy import text
    from app.database import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection OK")
    except Exception as exc:
        logger.error("PostgreSQL connection FAILED: %s", exc)
        raise


async def check_redis() -> None:
    """Verify Redis is reachable before starting (best-effort, won't abort)."""
    from app.config import settings

    if not settings.redis_url:
        logger.info("Redis not configured, skipping check")
        return

    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
        await client.ping()
        await client.aclose()
        logger.info("Redis connection OK")
    except Exception as exc:
        logger.warning("Redis connection FAILED (will use MemoryStorage): %s", exc)


async def main() -> None:
    logger.info("Checking connections...")
    await check_postgres()
    await check_redis()

    from app.presentation.bot.bot import get_bot_manager, initialize_bot, shutdown_bot

    await initialize_bot()
    try:
        await get_bot_manager().start_polling()
    finally:
        await shutdown_bot()


if __name__ == "__main__":
    asyncio.run(main())
