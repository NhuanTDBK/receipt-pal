"""Telegram test doubles used by backend tests."""

from tests.doubles.telegram import (
    FakeBot,
    FakeChat,
    FakeDocument,
    FakeFSMContext,
    FakeMessage,
    FakePhotoSize,
    FakeSentMessage,
    FakeTelegramUser,
)

__all__ = [
    "FakeBot",
    "FakeChat",
    "FakeDocument",
    "FakeFSMContext",
    "FakeMessage",
    "FakePhotoSize",
    "FakeSentMessage",
    "FakeTelegramUser",
]
