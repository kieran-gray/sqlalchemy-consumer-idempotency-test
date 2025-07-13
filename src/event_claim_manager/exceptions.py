class EventClaimException(Exception):
    """Base exception for event claim flows."""

    pass


class AlreadyCompletedError(EventClaimException):
    """Raised when an event has already been successfully processed."""

    pass


class LockContentionError(EventClaimException):
    """Raised when another consumer has a lock on the event."""

    pass
