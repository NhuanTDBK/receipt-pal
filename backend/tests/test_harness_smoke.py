from __future__ import annotations

import pytest

from tests.factories import (
    build_receipt_payload,
    create_conversation,
    create_receipt,
    create_user,
)


@pytest.mark.asyncio
async def test_fake_bot_round_trips_registered_files(fake_bot) -> None:
    fake_bot.register_file("photo-1", b"fake-image-bytes")

    file_ref = await fake_bot.get_file("photo-1")
    data = await fake_bot.download_file(file_ref.file_path)

    assert data.read() == b"fake-image-bytes"


@pytest.mark.asyncio
async def test_fake_message_and_state_capture_ui_updates(
    fake_message,
    fake_state,
) -> None:
    status = await fake_message.answer("Parsing...")
    await status.edit_text("Done")
    reply = await fake_message.reply("Saved")

    await fake_state.set_state("reviewing")
    await fake_state.update_data(draft={"total": 90000})

    assert len(fake_message.answers) == 1
    assert len(fake_message.replies) == 1
    assert status.text == "Done"
    assert reply.text == "Saved"
    assert await fake_state.get_data() == {"draft": {"total": 90000}}
    assert await fake_state.get_state() == "reviewing"


def test_build_receipt_payload_supports_overrides() -> None:
    payload = build_receipt_payload(
        merchant={"name": "Highlands Coffee"},
        total=75000,
        items=[
            {
                "name": "Latte",
                "amount": 75000,
                "quantity": 1,
                "food_tags": ["caffeine", "dairy"],
            }
        ],
    )

    assert payload["merchant"]["name"] == "Highlands Coffee"
    assert payload["total"] == 75000
    assert payload["currency"] == "VND"
    assert payload["items"][0]["name"] == "Latte"


@pytest.mark.asyncio
@pytest.mark.database
async def test_factories_can_persist_receipt_graph(db_session) -> None:
    user = await create_user(db_session, first_name="Harness")
    conversation = await create_conversation(db_session, user=user)
    receipt = await create_receipt(db_session, user=user, conversation=conversation)
    await db_session.commit()

    assert receipt.user_id == user.id
    assert receipt.conversation_id == conversation.id
    assert len(receipt.items) == 1
    assert receipt.items[0].name == "Trà sữa oolong"
