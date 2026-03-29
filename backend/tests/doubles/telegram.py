from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from types import SimpleNamespace
from typing import Any


@dataclass(slots=True)
class FakeTelegramUser:
    id: int = 123456
    username: str = "receipt-pal-tester"
    first_name: str = "Receipt"


@dataclass(slots=True)
class FakeChat:
    id: int = 987654


@dataclass(slots=True)
class FakePhotoSize:
    file_id: str


@dataclass(slots=True)
class FakeDocument:
    file_id: str
    mime_type: str = "application/pdf"
    file_size: int | None = None


@dataclass
class FakeSentMessage:
    text: str
    reply_markup: Any = None
    edits: list[dict[str, Any]] = field(default_factory=list)

    async def edit_text(
        self,
        text: str,
        reply_markup: Any = None,
        **kwargs: Any,
    ) -> "FakeSentMessage":
        self.text = text
        self.reply_markup = reply_markup
        self.edits.append(
            {"text": text, "reply_markup": reply_markup, "kwargs": kwargs}
        )
        return self


class FakeMessage:
    def __init__(
        self,
        *,
        text: str | None = None,
        from_user: FakeTelegramUser | None = None,
        chat: FakeChat | None = None,
        photo: list[FakePhotoSize] | None = None,
        document: FakeDocument | None = None,
        media_group_id: str | None = None,
    ) -> None:
        self.text = text
        self.from_user = from_user or FakeTelegramUser()
        self.chat = chat or FakeChat()
        self.photo = photo or []
        self.document = document
        self.media_group_id = media_group_id
        self.answers: list[FakeSentMessage] = []
        self.replies: list[FakeSentMessage] = []

    async def answer(
        self,
        text: str,
        reply_markup: Any = None,
        **kwargs: Any,
    ) -> FakeSentMessage:
        msg = FakeSentMessage(text=text, reply_markup=reply_markup)
        self.answers.append(msg)
        return msg

    async def reply(
        self,
        text: str,
        reply_markup: Any = None,
        **kwargs: Any,
    ) -> FakeSentMessage:
        msg = FakeSentMessage(text=text, reply_markup=reply_markup)
        self.replies.append(msg)
        return msg


class FakeFSMContext:
    def __init__(self) -> None:
        self.state: Any = None
        self.data: dict[str, Any] = {}

    async def set_state(self, state: Any) -> None:
        self.state = state

    async def get_state(self) -> Any:
        return self.state

    async def update_data(self, **kwargs: Any) -> None:
        self.data.update(kwargs)

    async def get_data(self) -> dict[str, Any]:
        return dict(self.data)

    async def clear(self) -> None:
        self.state = None
        self.data.clear()


class FakeBot:
    def __init__(self) -> None:
        self._file_paths: dict[str, str] = {}
        self._file_bytes: dict[str, bytes] = {}
        self.sent_messages: list[dict[str, Any]] = []

    def register_file(
        self,
        file_id: str,
        data: bytes,
        *,
        file_path: str | None = None,
    ) -> str:
        path = file_path or f"files/{file_id}"
        self._file_paths[file_id] = path
        self._file_bytes[path] = data
        return path

    async def get_file(self, file_id: str) -> Any:
        if file_id not in self._file_paths:
            raise FileNotFoundError(f"No fake file registered for {file_id}")
        return SimpleNamespace(file_path=self._file_paths[file_id])

    async def download_file(self, file_path: str) -> BytesIO:
        if file_path not in self._file_bytes:
            raise FileNotFoundError(f"No fake file bytes registered for {file_path}")
        return BytesIO(self._file_bytes[file_path])

    async def send_message(
        self,
        chat_id: int,
        text: str,
        **kwargs: Any,
    ) -> FakeSentMessage:
        msg = FakeSentMessage(text=text, reply_markup=kwargs.get("reply_markup"))
        self.sent_messages.append(
            {"chat_id": chat_id, "message": msg, "kwargs": kwargs}
        )
        return msg
