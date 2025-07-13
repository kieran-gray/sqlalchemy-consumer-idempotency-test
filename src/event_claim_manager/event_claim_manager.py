import hashlib
import logging

from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_claim_manager.exceptions import (
    AlreadyCompletedError,
    LockContentionError,
)
from src.event_claim_manager.table import (
    ProcessingStatus,
    consumer_processed_events_table,
)

log = logging.getLogger(__name__)


class SQLAlchemyEventClaimManager:
    """Claim manager used to ensure that events are only handled once."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_lock_key_for_event(self, event_id: str) -> int:
        hash = hashlib.sha256(event_id.encode()).digest()
        return int.from_bytes(hash[:8], signed=True)

    async def _acquire_advisory_lock(self, event_id: str) -> None:
        lock_key = await self._get_lock_key_for_event(event_id=event_id)
        log.debug(
            f"Attempting to acquire advisory lock for event {event_id} (key: {lock_key})"
        )

        stmt_advisory_lock = text("SELECT pg_try_advisory_xact_lock(:key)")
        result = await self._session.execute(stmt_advisory_lock, {"key": lock_key})

        if not result.scalar_one():
            raise LockContentionError(
                f"Event '{event_id}' is locked by another consumer."
            )

        log.debug(f"Advisory lock acquired for event: {event_id}")

    async def _get_event_processing_state(self, event_id: str) -> str | None:
        stmt_select = select(consumer_processed_events_table.c.status).where(
            consumer_processed_events_table.c.event_id == event_id
        )
        result = await self._session.execute(stmt_select)
        return result.scalar_one_or_none()

    async def _insert_event(self, event_id: str) -> None:
        stmt_insert = (
            insert(consumer_processed_events_table)
            .values(event_id=event_id, status=ProcessingStatus.PROCESSING)
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt_insert)

    async def try_claim_event(self, event_id: str) -> None:
        """
        Claims an event for processing using a non-blocking lock.

        Raises:
            AlreadyCompletedError: If the event was already completed.
            LockContentionError: If another process holds the lock.
        """
        await self._acquire_advisory_lock(event_id=event_id)

        current_state = await self._get_event_processing_state(event_id=event_id)

        if current_state == ProcessingStatus.COMPLETED:
            raise AlreadyCompletedError(f"Event '{event_id}' already completed.")

        if current_state is None:
            log.debug(f"Event ID '{event_id}' not found. Inserting new record.")
            await self._insert_event(event_id=event_id)

        log.info(f"Claim successfully established for Event '{event_id}'")

    async def mark_as_completed(self, event_id: str) -> None:
        """Marks the event as completed in the database."""
        stmt = (
            update(consumer_processed_events_table)
            .where(consumer_processed_events_table.c.event_id == event_id)
            .values(status=ProcessingStatus.COMPLETED)
        )
        await self._session.execute(stmt)
        log.info(f"Marked event '{event_id}' as COMPLETED within transaction.")
