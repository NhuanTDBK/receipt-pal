import uuid
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory


async def create_memory(
    session: AsyncSession, user_id: uuid.UUID, content: str
) -> Memory:
    """Persist a free-text note for the user."""
    memory = Memory(user_id=user_id, content=content)
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    return memory


async def list_memories(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    since: datetime | None = None,
    keywords: list[str] | None = None,
    limit: int = 50,
) -> list[Memory]:
    """Retrieve stored notes for the user.

    Args:
        since:    Only notes created after this timestamp.
        keywords: Only notes containing ALL keywords (case-insensitive).
        limit:    Max rows to return (newest first).
    """
    conditions = [Memory.user_id == user_id]

    if since is not None:
        conditions.append(Memory.created_at >= since)

    if keywords:
        for keyword in keywords:
            conditions.append(Memory.content.ilike(f"%{keyword}%"))

    result = await session.execute(
        select(Memory)
        .where(and_(*conditions))
        .order_by(Memory.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
