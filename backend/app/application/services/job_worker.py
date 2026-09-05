from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event, Thread

from app.domain.entities.job import Job


class JobWorker:
    def __init__(
        self,
        service,
        *,
        worker_id: str,
        handlers: dict[str, Callable[[Job], None]],
        lease_seconds: int = 60,
        heartbeat_seconds: float = 20,
        clock: Callable[[], datetime] | None = None,
    ):
        if heartbeat_seconds <= 0:
            raise ValueError('heartbeat_seconds must be positive')
        self._service = service
        self._worker_id = worker_id
        self._handlers = handlers
        self._lease_seconds = lease_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run_once(self, *, now: datetime | None = None) -> Job | None:
        moment = now or self._clock()
        job = self._service.lease_next(worker_id=self._worker_id, now=moment, lease_seconds=self._lease_seconds)
        if job is None:
            return None

        handler = self._handlers.get(job.kind)
        if handler is None:
            return self._service.fail(
                job.id,
                worker_id=self._worker_id,
                lease_token=job.lease_token,
                error=f'No handler registered for job kind: {job.kind}',
                now=moment,
            )

        stop_heartbeat = Event()
        heartbeat_errors: list[PermissionError] = []

        def renew_until_stopped() -> None:
            while not stop_heartbeat.wait(self._heartbeat_seconds):
                try:
                    self._service.renew_lease(
                        job.id,
                        worker_id=self._worker_id,
                        lease_token=job.lease_token,
                        now=self._clock(),
                        lease_seconds=self._lease_seconds,
                    )
                except PermissionError as error:
                    heartbeat_errors.append(error)
                    return

        heartbeat = Thread(target=renew_until_stopped, daemon=True)
        heartbeat.start()
        handler_error: Exception | None = None
        try:
            handler(job)
        except Exception as error:
            handler_error = error
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=self._heartbeat_seconds * 2)

        if heartbeat_errors:
            raise heartbeat_errors[0]
        completed_at = now or self._clock()
        if handler_error is not None:
            return self._service.fail(
                job.id,
                worker_id=self._worker_id,
                lease_token=job.lease_token,
                error=str(handler_error) or handler_error.__class__.__name__,
                now=completed_at,
            )

        return self._service.complete(
            job.id,
            worker_id=self._worker_id,
            lease_token=job.lease_token,
            now=completed_at,
        )
