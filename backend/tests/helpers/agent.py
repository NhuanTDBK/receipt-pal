from __future__ import annotations

import uuid

from agents import RunContextWrapper

from app.services.agent_context import TelegramAgentContext
from tests.doubles import FakeBot, FakeFSMContext, FakeMessage, FakeSentMessage


def build_run_context(
    *,
    db_session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    message_text: str = "test",
) -> RunContextWrapper[TelegramAgentContext]:
    context = TelegramAgentContext(
        bot=FakeBot(),
        message=FakeMessage(text=message_text),
        status_msg=FakeSentMessage(text="Working..."),
        state=FakeFSMContext(),
        db_session=db_session,
        user_id=user_id,
        conversation_id=conversation_id or uuid.uuid4(),
    )
    return RunContextWrapper(context=context)
