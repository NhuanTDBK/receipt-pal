from __future__ import annotations

import os

import pytest
from agents import Runner
from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession

from app.database import engine
from app.services.agent import build_receipt_agent, configure_provider
from app.services.agent_context import TelegramAgentContext
from tests.doubles import FakeBot, FakeFSMContext, FakeMessage, FakeSentMessage
from tests.factories import create_conversation, create_user
from tests.generators import build_generated_receipt_payload, seed_receipts

pytestmark = [pytest.mark.real_llm, pytest.mark.database]


def _require_real_llm() -> None:
    if os.environ.get("RUN_REAL_LLM_TESTS") != "1":
        pytest.skip("Set RUN_REAL_LLM_TESTS=1 to enable real-model verification.")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key == "test-openai-key":
        pytest.skip(
            "Set a real OPENAI_API_KEY or GEMINI_API_KEY to enable real-model verification."
        )


def _build_context(db_session, *, user_id, conversation_id, message_text: str):
    return TelegramAgentContext(
        bot=FakeBot(),
        message=FakeMessage(text=message_text),
        status_msg=FakeSentMessage(text="Working..."),
        state=FakeFSMContext(),
        db_session=db_session,
        user_id=user_id,
        conversation_id=conversation_id,
    )


def _final_text(result) -> str:
    output = result.final_output
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return str(output)


@pytest.mark.asyncio
async def test_real_llm_can_parse_text_receipt_into_draft(db_session) -> None:
    _require_real_llm()
    configure_provider()

    user = await create_user(db_session, first_name="Real Parse")
    conversation = await create_conversation(db_session, user=user)
    await db_session.commit()

    agent = build_receipt_agent()
    context = _build_context(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        message_text="parse receipt",
    )
    memory_session = SQLAlchemySession(
        str(conversation.id), engine=engine, create_tables=True
    )

    await Runner.run(
        agent,
        (
            "This is a purchase list. Do not ask questions. "
            "Parse it immediately as a receipt: cà phê sữa 35k"
        ),
        context=context,
        session=memory_session,
    )

    assert context.draft is not None
    assert context.draft["total"] == 35000
    assert context.draft["items"]
    assert "35" in context.status_msg.text


@pytest.mark.asyncio
async def test_real_llm_can_answer_search_question_from_seeded_receipts(
    db_session,
) -> None:
    _require_real_llm()
    configure_provider()

    user = await create_user(db_session, first_name="Real Search")
    conversation = await create_conversation(db_session, user=user)
    await seed_receipts(
        db_session,
        user=user,
        conversation=conversation,
        payloads=[
            build_generated_receipt_payload(
                category="cafe",
                merchant_name="Phê La",
                total=60000,
            ),
            build_generated_receipt_payload(
                category="grocery",
                merchant_name="WinMart+",
                total=90000,
                index=1,
            ),
        ],
    )
    await db_session.commit()

    agent = build_receipt_agent()
    context = _build_context(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        message_text="search receipts",
    )
    memory_session = SQLAlchemySession(
        str(conversation.id), engine=engine, create_tables=True
    )

    result = await Runner.run(
        agent,
        "Show me only my Phê La receipts. Mention the merchant name and the total. Keep it brief.",
        context=context,
        session=memory_session,
    )
    text = _final_text(result)

    assert text
    assert "Phê La" in text
    assert any(token in text for token in ["60000", "60,000", "60.000"])


@pytest.mark.asyncio
async def test_real_llm_can_answer_category_analytics_from_seeded_data(
    db_session,
) -> None:
    _require_real_llm()
    configure_provider()

    user = await create_user(db_session, first_name="Real Analytics")
    conversation = await create_conversation(db_session, user=user)
    await seed_receipts(
        db_session,
        user=user,
        conversation=conversation,
        payloads=[
            build_generated_receipt_payload(category="cafe", total=60000),
            build_generated_receipt_payload(category="grocery", total=120000, index=1),
        ],
    )
    await db_session.commit()

    agent = build_receipt_agent()
    context = _build_context(
        db_session,
        user_id=user.id,
        conversation_id=conversation.id,
        message_text="analytics",
    )
    memory_session = SQLAlchemySession(
        str(conversation.id), engine=engine, create_tables=True
    )

    result = await Runner.run(
        agent,
        (
            "What are my spending categories and totals? "
            "Mention cafe and grocery explicitly and keep the answer brief."
        ),
        context=context,
        session=memory_session,
    )
    text = _final_text(result).lower()

    assert text
    assert "cafe" in text
    assert "grocery" in text
