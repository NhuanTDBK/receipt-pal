from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import Base


def _is_sqlite(engine: AsyncEngine) -> bool:
    """Check if the engine is using SQLite."""
    return "sqlite" in str(engine.url).lower()


def _truncate_statement(engine: AsyncEngine) -> list[str]:
    """Generate statements to clear all tables."""
    table_names = [table.name for table in reversed(Base.metadata.sorted_tables)]
    if not table_names:
        return []

    if _is_sqlite(engine):
        # SQLite doesn't support TRUNCATE, use DELETE FROM
        return [f"DELETE FROM {name}" for name in table_names]
    else:
        # PostgreSQL
        quoted_names = [f'"{name}"' for name in table_names]
        return [f"TRUNCATE {', '.join(quoted_names)} RESTART IDENTITY CASCADE"]


async def prepare_database(engine: AsyncEngine) -> None:
    """Ensure the test schema exists and the database is reachable."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
        await conn.run_sync(Base.metadata.create_all)


async def reset_database(engine: AsyncEngine) -> None:
    """Clear all mapped tables between tests."""
    statements = _truncate_statement(engine)
    if not statements:
        return

    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
