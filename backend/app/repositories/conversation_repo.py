import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.conversation import Conversation, ConversationMessage


async def get_active_conversation(session: AsyncSession, user_id: uuid.UUID) -> Conversation:
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
    now = datetime.now(UTC)

    if conversation is None or (now - conversation.last_message_at.replace(tzinfo=UTC)) > timeout:
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
        conversation.last_message_at = datetime.now(UTC)

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
