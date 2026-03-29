from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import agent_runner
from tests.factories import build_conversation, build_user


def _make_usage(
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def _patch_runner_dependencies(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    db_user = build_user(telegram_id=4242, username="agent-runner", first_name="Agent")
    conversation = build_conversation(user_id=db_user.id)
    user_settings = SimpleNamespace(
        language="en",
        response_preference="concise",
        location="HCMC",
    )
    fake_agent = object()
    fake_agent_session = object()

    user_repo_mock = AsyncMock(return_value=db_user)
    conversation_repo_mock = AsyncMock(return_value=conversation)
    settings_repo_mock = AsyncMock(return_value=user_settings)
    add_token_usage_mock = AsyncMock()

    monkeypatch.setattr(agent_runner, "_ensure_provider_configured", lambda: None)
    monkeypatch.setattr(
        agent_runner,
        "build_receipt_agent",
        lambda settings: fake_agent,
    )
    monkeypatch.setattr(
        agent_runner,
        "SQLAlchemySession",
        lambda *args, **kwargs: fake_agent_session,
    )
    monkeypatch.setattr(agent_runner.user_repo, "get_or_create_user", user_repo_mock)
    monkeypatch.setattr(
        agent_runner.conversation_repo,
        "get_active_conversation",
        conversation_repo_mock,
    )
    monkeypatch.setattr(
        agent_runner.user_settings_repo,
        "get_or_create_settings",
        settings_repo_mock,
    )
    monkeypatch.setattr(
        agent_runner.conversation_repo,
        "add_token_usage",
        add_token_usage_mock,
    )

    return SimpleNamespace(
        db_user=db_user,
        conversation=conversation,
        user_settings=user_settings,
        agent=fake_agent,
        agent_session=fake_agent_session,
        user_repo=user_repo_mock,
        conversation_repo=conversation_repo_mock,
        settings_repo=settings_repo_mock,
        add_token_usage=add_token_usage_mock,
    )


def test_build_input_returns_plain_text_for_text_only() -> None:
    assert agent_runner._build_input("hello") == "hello"


def test_build_input_encodes_multimodal_content() -> None:
    input_data = agent_runner._build_input(
        "parse this",
        images=[b"image-bytes"],
        pdfs=[b"%PDF-1.7"],
    )

    assert isinstance(input_data, list)
    assert input_data[0]["role"] == "user"
    parts = input_data[0]["content"]
    assert parts[0] == {"type": "input_text", "text": "parse this"}
    assert parts[1]["type"] == "input_image"
    assert parts[1]["image_url"].startswith("data:image/jpeg;base64,")
    assert parts[2]["type"] == "input_image"
    assert parts[2]["image_url"].startswith("data:application/pdf;base64,")


@pytest.mark.asyncio
async def test_run_agent_tracks_token_usage_and_sends_final_text(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot,
    fake_message,
    fake_state,
) -> None:
    deps = _patch_runner_dependencies(monkeypatch)
    captured: dict[str, object] = {}

    async def fake_runner_run(agent, input_data, *, context, session):
        captured["agent"] = agent
        captured["input_data"] = input_data
        captured["context"] = context
        captured["session"] = session
        return SimpleNamespace(
            raw_responses=[
                SimpleNamespace(
                    usage=_make_usage(prompt_tokens=11, completion_tokens=3)
                ),
                SimpleNamespace(usage=_make_usage(input_tokens=5, output_tokens=7)),
            ],
            final_output="Parsed successfully",
        )

    monkeypatch.setattr(agent_runner.Runner, "run", fake_runner_run)

    db_session = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()
    status_msg = await fake_message.answer("Working...")

    await agent_runner.run_agent(
        fake_bot,
        fake_message,
        status_msg,
        db_session,
        fake_state,
        user_input="How much did I spend?",
        images=[b"receipt-image"],
    )

    deps.user_repo.assert_awaited_once_with(
        db_session,
        telegram_id=fake_message.from_user.id,
        username=fake_message.from_user.username,
        first_name=fake_message.from_user.first_name,
    )
    deps.conversation_repo.assert_awaited_once_with(db_session, deps.db_user.id)
    deps.settings_repo.assert_awaited_once_with(db_session, deps.db_user.id)
    deps.add_token_usage.assert_awaited_once_with(
        db_session,
        conversation_id=deps.conversation.id,
        input_tokens=16,
        output_tokens=10,
    )

    assert captured["agent"] is deps.agent
    assert captured["session"] is deps.agent_session
    assert captured["input_data"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "How much did I spend?"},
                {
                    "type": "input_image",
                    "image_url": captured["input_data"][0]["content"][1]["image_url"],
                },
            ],
        }
    ]
    assert captured["context"].user_id == deps.db_user.id
    assert captured["context"].conversation_id == deps.conversation.id
    assert fake_message.answers[-1].text == "Parsed successfully"
    assert db_session.commit.await_count == 2


@pytest.mark.asyncio
async def test_run_agent_skips_redundant_final_text_when_tools_handle_ui(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot,
    fake_message,
    fake_state,
) -> None:
    _patch_runner_dependencies(monkeypatch)

    async def fake_runner_run(agent, input_data, *, context, session):
        context.suppress_final_text = True
        return SimpleNamespace(raw_responses=[], final_output="Should stay hidden")

    monkeypatch.setattr(agent_runner.Runner, "run", fake_runner_run)

    db_session = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()
    status_msg = await fake_message.answer("Working...")

    await agent_runner.run_agent(
        fake_bot,
        fake_message,
        status_msg,
        db_session,
        fake_state,
        user_input="show me the draft",
    )

    assert [message.text for message in fake_message.answers] == ["Working..."]


@pytest.mark.asyncio
async def test_run_agent_handles_runner_failures(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot,
    fake_message,
    fake_state,
) -> None:
    _patch_runner_dependencies(monkeypatch)

    async def fake_runner_run(agent, input_data, *, context, session):
        raise RuntimeError("boom")

    monkeypatch.setattr(agent_runner.Runner, "run", fake_runner_run)

    db_session = AsyncMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()
    status_msg = await fake_message.answer("Working...")
    await fake_state.set_state("reviewing")
    await fake_state.update_data(draft={"total": 1000})

    await agent_runner.run_agent(
        fake_bot,
        fake_message,
        status_msg,
        db_session,
        fake_state,
        user_input="please retry",
    )

    assert status_msg.text == "⚠️ Failed to process. Please try again."
    assert await fake_state.get_state() is None
    assert await fake_state.get_data() == {}
