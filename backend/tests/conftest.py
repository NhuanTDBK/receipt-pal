from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

from tests.doubles import FakeBot, FakeFSMContext, FakeMessage  # noqa: E402
from tests.helpers import prepare_database, reset_database  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "database: requires a reachable PostgreSQL test database",
    )
    config.addinivalue_line(
        "markers",
        "real_llm: requires explicit real-model credentials and opt-in",
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    # Require TEST_DATABASE_URL environment variable
    database_url = os.environ.get("TEST_DATABASE_URL")

    if not database_url:
        pytest.exit(
            "TEST_DATABASE_URL environment variable is required. "
            "Set it in your .env file or environment."
        )

    test_engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
    )

    try:
        await prepare_database(test_engine)
    except Exception as exc:  # pragma: no cover - depends on local services
        await test_engine.dispose()
        pytest.exit(f"Test database unavailable at {database_url}: {exc}")

    yield test_engine

    await test_engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    await reset_database(db_engine)

    # Create a fresh session factory bound to the test engine
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await reset_database(db_engine)


@pytest.fixture
def db_sessionmaker(db_engine: AsyncEngine):
    return async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def fake_message() -> FakeMessage:
    return FakeMessage(text="hello")


@pytest.fixture
def fake_state() -> FakeFSMContext:
    return FakeFSMContext()
