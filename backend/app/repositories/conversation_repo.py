import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.conversation import Conversation, ConversationMessage


async def get_active_conversation(
    session: AsyncSession, user_id: uuid.UUID
) -> Conversation:
    """Return the active conversation for the user, or create a new one.

    A new conversation is started if no active conversation exists or if the last
    message was more than `conversation_timeout_minutes` ago.
    """
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id, Conversation.is_active.is_(True))
        .order_by(Conversation.last_message_at.desc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()

    timeout = timedelta(minutes=settings.conversation_timeout_minutes)
    now = datetime.now(timezone.utc)

    if (
        conversation is None
        or (now - conversation.last_message_at.replace(tzinfo=timezone.utc)) > timeout
    ):
        if conversation is not None:
            conversation.is_active = False
            await session.flush()

        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=user_id,
            started_at=now,
            last_message_at=now,
            is_active=True,
        )
        session.add(conversation)
        await session.flush()

    return conversation


async def append_message(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    content: str | None = None,
    image_file_ids: list[str] | None = None,
    tool_name: str | None = None,
    tool_args: dict | None = None,
) -> ConversationMessage:
    """Append a message to the conversation and update last_message_at."""
    msg = ConversationMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        image_file_ids=image_file_ids,
        tool_name=tool_name,
        tool_args=tool_args,
    )
    session.add(msg)

    await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    result = await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation:
        conversation.last_message_at = datetime.now(timezone.utc)

    await session.flush()
    return msg


async def load_history(
    session: AsyncSession, conversation_id: uuid.UUID
) -> list[ConversationMessage]:
    """Load all messages for a conversation in chronological order."""
    result = await session.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    return list(result.scalars().all())


async def add_token_usage(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Atomically increment token counters on a conversation row.

    Uses SQL column arithmetic (col + :delta) to avoid race conditions when
    multiple parse calls occur concurrently on the same conversation.
    """
    if input_tokens == 0 and output_tokens == 0:
        return

    await session.execute(
        sa_update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            input_tokens=Conversation.input_tokens + input_tokens,
            output_tokens=Conversation.output_tokens + output_tokens,
            total_tokens=Conversation.total_tokens + input_tokens + output_tokens,
        )
    )
    await session.flush()


async def get_usage_stats(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    """Return aggregated token usage across all conversations for a user."""
    result = await session.execute(
        select(
            func.coalesce(func.sum(Conversation.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(Conversation.output_tokens), 0).label(
                "output_tokens"
            ),
            func.coalesce(func.sum(Conversation.total_tokens), 0).label("total_tokens"),
            func.count(Conversation.id).label("conversation_count"),
        ).where(Conversation.user_id == user_id)
    )
    row = result.one()
    return {
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "total_tokens": row.total_tokens,
        "conversation_count": row.conversation_count,
    }
