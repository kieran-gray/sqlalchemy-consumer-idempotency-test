import logging
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


class SQLAlchemyUnitOfWork:
    """
    SQLAlchemy implementation of the Unit of Work pattern.

    Manages database transactions and ensures data consistency
    by coordinating multiple repository operations within a single transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize the Unit of Work with an async SQLAlchemy session.

        Args:
            session: The async SQLAlchemy session to manage
        """
        self._session = session

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        log.debug("UnitOfWork context entered")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        Exit the async context manager.

        Automatically commits on success or rolls back on exception.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred

        Returns:
            None to propagate exceptions, or True to suppress them
        """
        try:
            if exc_type is not None:
                log.warning(
                    f"Exception in UnitOfWork context: {exc_type.__name__}: {exc_val}"
                )
                await self.rollback()
            else:
                await self.commit()
        except Exception as e:
            log.error(f"Error in UnitOfWork cleanup: {e}")
            raise
        finally:
            log.debug("UnitOfWork context exited")
        return None

    async def commit(self) -> None:
        """
        Commit the current transaction.

        Raises:
            RuntimeError: If the unit of work is not active
            SQLAlchemyError: If the commit fails
        """
        await self._session.commit()

    async def rollback(self) -> None:
        """
        Roll back the current transaction.

        Raises:
            SQLAlchemyError: If the rollback fails
        """
        await self._session.rollback()
