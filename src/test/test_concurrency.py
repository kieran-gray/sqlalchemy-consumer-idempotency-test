import asyncio
import logging
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.event_claim_manager.exceptions import (
    AlreadyCompletedError,
    LockContentionError,
)
from src.event_claim_manager.event_claim_manager import SQLAlchemyEventClaimManager
from src.event_claim_manager.table import (
    ProcessingStatus,
    consumer_processed_events_table,
)
from src.event_claim_manager.unit_of_work import SQLAlchemyUnitOfWork

from src.test.conftest import new_consumer_session

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)


async def test_consumer_b_cannot_lock_when_a_holds_lock(
    uow: SQLAlchemyUnitOfWork,
    event_claim_manager: SQLAlchemyEventClaimManager,
    dsn: str,
):
    """
    Tests that Consumer B gets a LockContentionError when trying to claim an
    event that Consumer A has already locked within a transaction.
    """
    event_id = str(uuid4())

    async def consumer_a_behavior():
        log.info("[Consumer A] Starting, will acquire lock")
        async with uow:
            await event_claim_manager.try_claim_event(event_id)
            await asyncio.sleep(2)
            await event_claim_manager.mark_as_completed(event_id)
        log.info("[Consumer A] Transaction committed")

    async def consumer_b_behavior():
        await asyncio.sleep(0.5)
        log.info("[Consumer B] Starting, will attempt to acquire lock")

        async with new_consumer_session(dsn) as session_b:
            uow_b = SQLAlchemyUnitOfWork(session_b)
            event_claim_manager_b = SQLAlchemyEventClaimManager(session_b)
            async with uow_b:
                with pytest.raises(LockContentionError) as exc_info:
                    await event_claim_manager_b.try_claim_event(event_id)
                log.info(f"[Consumer B] Caught expected error: {exc_info.value}")

    await asyncio.gather(consumer_a_behavior(), consumer_b_behavior())


async def test_consumer_b_cannot_lock_when_a_has_processed(
    uow: SQLAlchemyUnitOfWork,
    event_claim_manager: SQLAlchemyEventClaimManager,
    dsn: str,
):
    """
    Tests that Consumer B gets a AlreadyCompletedError when trying to claim an
    event that Consumer A has already processed.
    """
    event_id = str(uuid4())

    async def consumer_a_behavior():
        log.info("[Consumer A] Starting, will acquire lock")
        async with uow:
            await event_claim_manager.try_claim_event(event_id)
            await event_claim_manager.mark_as_completed(event_id)
        log.info("[Consumer A] Transaction committed")

    async def consumer_b_behavior():
        await asyncio.sleep(0.5)
        log.info("[Consumer B] Starting, will attempt to acquire lock")

        async with new_consumer_session(dsn) as session_b:
            uow_b = SQLAlchemyUnitOfWork(session_b)
            event_claim_manager_b = SQLAlchemyEventClaimManager(session_b)
            async with uow_b:
                with pytest.raises(AlreadyCompletedError) as exc_info:
                    await event_claim_manager_b.try_claim_event(event_id)
                log.info(f"[Consumer B] Caught expected error: {exc_info.value}")

    await asyncio.gather(consumer_a_behavior(), consumer_b_behavior())


async def test_consumer_b_can_process_after_a_fails_and_rolls_back(
    uow: SQLAlchemyUnitOfWork,
    event_claim_manager: SQLAlchemyEventClaimManager,
    dsn: str,
    session_maker: async_sessionmaker,
):
    """
    Tests that if Consumer A claims an event but its transaction fails,
    Consumer B can then successfully claim and process the event.
    """
    event_id = str(uuid4())

    async def consumer_a_behavior():
        log.info("[Consumer A] Starting, will acquire lock and then fail")
        with pytest.raises(ValueError, match="Simulating a processing failure"):
            async with uow:
                await event_claim_manager.try_claim_event(event_id)
                log.info("[Consumer A] Lock acquired, now raising error")
                raise ValueError("Simulating a processing failure")
        log.info("[Consumer A] Caught exception, UoW rolled back")

    async def consumer_b_behavior():
        await asyncio.sleep(0.5)
        log.info("[Consumer B] Starting, will attempt to acquire lock")
        async with new_consumer_session(dsn) as session_b:
            uow_b = SQLAlchemyUnitOfWork(session_b)
            event_claim_manager_b = SQLAlchemyEventClaimManager(session_b)
            async with uow_b:
                await event_claim_manager_b.try_claim_event(event_id)
                await event_claim_manager_b.mark_as_completed(event_id)
            log.info("[Consumer B] Transaction committed successfully")

    await asyncio.gather(consumer_a_behavior(), consumer_b_behavior())

    async with session_maker() as session:
        stmt = select(consumer_processed_events_table.c.status).where(
            consumer_processed_events_table.c.event_id == event_id
        )
        final_status = (await session.execute(stmt)).scalar_one()
        assert final_status == ProcessingStatus.COMPLETED
