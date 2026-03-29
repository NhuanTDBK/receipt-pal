from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import Base


def _truncate_statement() -> str | None:
    table_names = [f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables)]
    if not table_names:
        return None
    return f"TRUNCATE {', '.join(table_names)} RESTART IDENTITY CASCADE"


async def prepare_database(engine: AsyncEngine) -> None:
    """Ensure the test schema exists and the database is reachable."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
        await conn.run_sync(Base.metadata.create_all)


async def reset_database(engine: AsyncEngine) -> None:
    """Clear all mapped tables between tests."""
    statement = _truncate_statement()
    if not statement:
        return

    async with engine.begin() as conn:
        await conn.execute(text(statement))
