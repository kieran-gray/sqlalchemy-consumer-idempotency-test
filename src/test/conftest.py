from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.event_claim_manager.event_claim_manager import SQLAlchemyEventClaimManager
from src.event_claim_manager.table import metadata
from src.event_claim_manager.unit_of_work import SQLAlchemyUnitOfWork


@pytest.fixture()
def dsn() -> str:
    """The database connection string."""
    return "postgresql+asyncpg://postgres:password@localhost:5432/test"


@pytest_asyncio.fixture
async def engine(dsn: str) -> AsyncGenerator[AsyncEngine, None]:
    """Create a single engine instance for the entire test session."""
    async_engine = create_async_engine(url=dsn)
    yield async_engine
    await async_engine.dispose()


@pytest.fixture
def session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a single session_maker for the entire test session."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean, isolated session for each test function."""
    async with session_maker() as session:
        yield session


@pytest.fixture
def uow(db_session: AsyncSession) -> SQLAlchemyUnitOfWork:
    """Provide a Unit of Work instance for the current test's session."""
    return SQLAlchemyUnitOfWork(db_session)


@pytest.fixture
def event_claim_manager(db_session: AsyncSession) -> SQLAlchemyEventClaimManager:
    """Provide an EventClaimManager instance for the current test's session."""
    return SQLAlchemyEventClaimManager(db_session)


@pytest_asyncio.fixture(autouse=True)
async def clean_db_tables(engine: AsyncEngine):
    """
    Function-scoped fixture to ensure a clean database for each test.
    This runs automatically before each test function.
    """
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all, checkfirst=True)
        await conn.run_sync(metadata.create_all)
    yield


@asynccontextmanager
async def new_consumer_session(dsn: str) -> AsyncGenerator[AsyncSession, None]:
    """
    A helper context manager to create a temporary, independent engine and session
    for simulating a separate consumer (like Consumer B).
    """
    engine = create_async_engine(url=dsn)
    session_maker = async_sessionmaker(engine)
    try:
        async with session_maker() as session:
            yield session
    finally:
        await engine.dispose()
