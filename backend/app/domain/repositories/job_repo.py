class JobConflictError(RuntimeError):
    """Repository-level idempotency conflict without exposing ORM exceptions."""

