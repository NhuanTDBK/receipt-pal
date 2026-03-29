from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://receipt_pal:receipt_pal@localhost:5432/receipt_pal_test",
)

# Force a test-specific configuration before importing app modules.
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-telegram-token")
os.environ.setdefault(
    "OPENAI_API_KEY",
    os.environ.get("GEMINI_API_KEY", "test-openai-key"),
)
os.environ.setdefault(
    "OPENAI_BASE_URL",
    os.environ.get("GEMINI_BASE_URL", "https://example.invalid/v1"),
)
os.environ.setdefault("MODEL", os.environ.get("GEMINI_MODEL", "test-model"))
os.environ.setdefault("ROCKSDB_PATH", "/tmp/receipt-pal-rocksdb-tests")

import app.models  # noqa: F401
from app.database import async_session_factory, engine
from tests.doubles import FakeBot, FakeFSMContext, FakeMessage
from tests.helpers import prepare_database, reset_database


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "database: requires a reachable PostgreSQL test database",
    )
    config.addinivalue_line(
        "markers",
        "real_llm: requires explicit real-model credentials and opt-in",
    )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _TEST_DATABASE_URL


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    try:
        await prepare_database(engine)
    except Exception as exc:  # pragma: no cover - depends on local services
        pytest.skip(
            f"PostgreSQL test database unavailable at {_TEST_DATABASE_URL!r}: {exc}"
        )

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    await reset_database(db_engine)
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await reset_database(db_engine)


@pytest.fixture
def db_sessionmaker(db_engine: AsyncEngine):
    return async_session_factory


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def fake_message() -> FakeMessage:
    return FakeMessage(text="hello")


@pytest.fixture
def fake_state() -> FakeFSMContext:
    return FakeFSMContext()
