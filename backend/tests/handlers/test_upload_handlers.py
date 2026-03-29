from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.presentation.bot.handlers import document as document_handler
from app.presentation.bot.handlers import photo as photo_handler
from tests.doubles import FakeDocument, FakeMessage, FakePhotoSize


class InMemoryPhotoStore:
    def __init__(self, initial: dict[str, bytes] | None = None) -> None:
        self.data = dict(initial or {})

    def get(self, file_id: str) -> bytes | None:
        return self.data.get(file_id)

    def store(self, file_id: str, image_bytes: bytes) -> None:
        self.data[file_id] = image_bytes


@pytest.fixture(autouse=True)
def reset_media_group_state():
    photo_handler._media_group_buffer.clear()
    photo_handler._media_group_locks.clear()
    tasks = list(photo_handler._media_group_tasks.values())
    photo_handler._media_group_tasks.clear()
    for task in tasks:
        task.cancel()

    yield

    tasks = list(photo_handler._media_group_tasks.values())
    photo_handler._media_group_buffer.clear()
    photo_handler._media_group_locks.clear()
    photo_handler._media_group_tasks.clear()
    for task in tasks:
        task.cancel()


@pytest.mark.asyncio
async def test_get_or_download_image_prefers_cached_bytes(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot,
) -> None:
    store = InMemoryPhotoStore({"cached-photo": b"cached-image"})
    monkeypatch.setattr(photo_handler.PhotoStore, "get_instance", lambda: store)
    fake_bot.get_file = AsyncMock(side_effect=AssertionError("cache should be used"))

    data = await photo_handler._get_or_download_image(fake_bot, "cached-photo")

    assert data == b"cached-image"


@pytest.mark.asyncio
async def test_process_receipt_runs_agent_for_photo_upload(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot,
    fake_message,
    fake_state,
) -> None:
    run_agent_mock = AsyncMock()
    monkeypatch.setattr(
        photo_handler,
        "_get_or_download_image",
        AsyncMock(return_value=b"photo-bytes"),
    )
    monkeypatch.setattr(photo_handler, "run_agent", run_agent_mock)

    session = object()
    await photo_handler._process_receipt(
        fake_message,
        ["photo-1"],
        session,
        fake_state,
        fake_bot,
    )

    assert fake_message.answers[0].text == "🔍 Parsing your receipt..."
    run_agent_mock.assert_awaited_once_with(
        fake_bot,
        fake_message,
        fake_message.answers[0],
        session,
        fake_state,
        "Here is a receipt photo. Please parse it.",
        images=[b"photo-bytes"],
    )


@pytest.mark.asyncio
async def test_process_receipt_runs_agent_for_pdf_upload(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot,
    fake_message,
    fake_state,
) -> None:
    run_agent_mock = AsyncMock()
    monkeypatch.setattr(
        photo_handler,
        "_get_or_download_image",
        AsyncMock(return_value=b"%PDF-1.7"),
    )
    monkeypatch.setattr(photo_handler, "run_agent", run_agent_mock)

    session = object()
    await photo_handler._process_receipt(
        fake_message,
        ["pdf-1"],
        session,
        fake_state,
        fake_bot,
        is_pdf=True,
    )

    assert fake_message.answers[0].text == "🔍 Parsing your PDF receipt…"
    run_agent_mock.assert_awaited_once_with(
        fake_bot,
        fake_message,
        fake_message.answers[0],
        session,
        fake_state,
        "Here is a PDF receipt. Please parse it.",
        pdfs=[b"%PDF-1.7"],
    )


@pytest.mark.asyncio
async def test_process_receipt_reports_download_failure(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot,
    fake_message,
    fake_state,
) -> None:
    monkeypatch.setattr(
        photo_handler,
        "_get_or_download_image",
        AsyncMock(return_value=None),
    )

    await photo_handler._process_receipt(
        fake_message,
        ["missing-file"],
        object(),
        fake_state,
        fake_bot,
    )

    assert [message.text for message in fake_message.answers] == [
        "⚠️ Could not download the photo. Please try again."
    ]


@pytest.mark.asyncio
async def test_handle_photo_buffers_media_group_before_processing(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot,
    fake_state,
) -> None:
    release = asyncio.Event()
    process_receipt_mock = AsyncMock()

    async def controlled_sleep(_delay: float) -> None:
        await release.wait()

    monkeypatch.setattr(photo_handler.asyncio, "sleep", controlled_sleep)
    monkeypatch.setattr(photo_handler, "_process_receipt", process_receipt_mock)

    message_one = FakeMessage(
        photo=[FakePhotoSize("photo-1")],
        media_group_id="group-1",
    )
    message_two = FakeMessage(
        photo=[FakePhotoSize("photo-2")],
        media_group_id="group-1",
    )

    await photo_handler.handle_photo(message_one, object(), fake_state, fake_bot)
    await photo_handler.handle_photo(message_two, object(), fake_state, fake_bot)

    task = photo_handler._media_group_tasks["group-1"]
    release.set()
    await task

    process_receipt_mock.assert_awaited_once()
    assert process_receipt_mock.await_args.args[1] == ["photo-1", "photo-2"]


@pytest.mark.asyncio
async def test_handle_pdf_rejects_oversized_documents(
    fake_bot,
    fake_state,
) -> None:
    message = FakeMessage(
        document=FakeDocument(
            file_id="pdf-oversized",
            file_size=document_handler.MAX_PDF_SIZE_BYTES + 1,
        )
    )

    await document_handler.handle_pdf(message, object(), fake_state, fake_bot)

    assert [reply.text for reply in message.replies] == [
        "That PDF is too large to process (max 20 MB). Try sending a compressed version."
    ]


@pytest.mark.asyncio
async def test_handle_pdf_delegates_to_shared_receipt_processor(
    monkeypatch: pytest.MonkeyPatch,
    fake_bot,
    fake_state,
) -> None:
    process_receipt_mock = AsyncMock()
    monkeypatch.setattr(
        document_handler,
        "_get_or_download_image",
        AsyncMock(return_value=b"%PDF-1.7"),
    )
    monkeypatch.setattr(document_handler, "_process_receipt", process_receipt_mock)

    message = FakeMessage(document=FakeDocument(file_id="pdf-1", file_size=1024))
    session = object()

    await document_handler.handle_pdf(message, session, fake_state, fake_bot)

    process_receipt_mock.assert_awaited_once_with(
        message,
        ["pdf-1"],
        session,
        fake_state,
        fake_bot,
        is_pdf=True,
    )


@pytest.mark.asyncio
async def test_handle_unsupported_document_replies_helpfully() -> None:
    message = FakeMessage(
        document=FakeDocument(file_id="doc-1", mime_type="application/msword")
    )

    await document_handler.handle_unsupported_document(message)

    assert [reply.text for reply in message.replies] == [
        "I can only process PDF files and photos. Please send your receipt as a PDF or a photo. 📸"
    ]
