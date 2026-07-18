import hashlib
import hmac
import json
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.ports.http import OutboundHttpResponse, WebhookSender
from app.core.pagination import paginated_result
from app.core.config import settings
from app.core.redaction import sanitize_error
from app.domain.entities.event_delivery import EventDelivery, EventDeliveryAttempt, PreparedEventDelivery
from app.domain.repositories.event_delivery_repo import EventDeliveryRepository
from app.domain.repositories.event_delivery_repo import EventDeliveryConflictError


@dataclass(frozen=True)
class EventDeliveryStreamEvent:
    id: str
    event: str
    tenant_id: str
    data: dict


class EventDeliveryStreamBroker:
    def __init__(self, max_recent: int = 200):
        self._max_recent = max_recent
        self._recent: list[EventDeliveryStreamEvent] = []
        self._subscribers: dict[str, tuple[str | None, asyncio.Queue[EventDeliveryStreamEvent]]] = {}

    def publish(self, event: EventDeliveryStreamEvent) -> None:
        self._recent.append(event)
        if len(self._recent) > self._max_recent:
            self._recent = self._recent[-self._max_recent:]
        for tenant_filter, queue in list(self._subscribers.values()):
            if tenant_filter is not None and tenant_filter != event.tenant_id:
                continue
            queue.put_nowait(event)

    def recent_events(self, tenant_id: str | None = None, limit: int = 20) -> list[EventDeliveryStreamEvent]:
        events = self._recent if tenant_id is None else [item for item in self._recent if item.tenant_id == tenant_id]
        return events[-limit:]

    def subscribe(self, tenant_id: str | None = None) -> tuple[str, asyncio.Queue[EventDeliveryStreamEvent]]:
        subscriber_id = uuid4().hex
        queue: asyncio.Queue[EventDeliveryStreamEvent] = asyncio.Queue()
        self._subscribers[subscriber_id] = (tenant_id, queue)
        return subscriber_id, queue

    def unsubscribe(self, subscriber_id: str) -> None:
        self._subscribers.pop(subscriber_id, None)


event_delivery_stream_broker = EventDeliveryStreamBroker()


def get_event_delivery_stream_broker() -> EventDeliveryStreamBroker:
    return event_delivery_stream_broker


class EventDeliveryService:
    def __init__(
        self,
        repo: EventDeliveryRepository | None = None,
        signing_secret: str | None = None,
        retry_base_seconds: int = 30,
        stream_broker: EventDeliveryStreamBroker | None = None,
        sender: WebhookSender | None = None,
    ):
        self._repo = repo
        self._signing_secret = signing_secret or settings.SECRET_KEY or 'dev-secret-key-32-bytes-minimum'
        self._retry_base_seconds = retry_base_seconds
        self._stream_broker = stream_broker or event_delivery_stream_broker
        self._sender = sender

    def prepare(self, *, event_type: str, tenant_id: str, payload: dict) -> PreparedEventDelivery:
        event_id = uuid4().hex
        body = json.dumps(
            {
                'event_id': event_id,
                'event_type': event_type,
                'tenant_id': tenant_id,
                'payload': payload,
            },
            ensure_ascii=False,
            separators=(',', ':'),
        )
        signature = hmac.new(
            self._signing_secret.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        return PreparedEventDelivery(
            event_id=event_id,
            event_type=event_type,
            tenant_id=tenant_id,
            body=body,
            headers={
                'Content-Type': 'application/json',
                'X-Legado-Event-Id': event_id,
                'X-Legado-Signature': f'sha256={signature}',
            },
        )

    def enqueue_webhook(
        self,
        *,
        event_type: str,
        tenant_id: str,
        payload: dict,
        target_url: str,
        dedupe_key: str | None = None,
    ) -> EventDelivery:
        if self._repo is None:
            raise RuntimeError('event delivery repository is not configured')
        if dedupe_key:
            existing = self._repo.get_by_dedupe_key(tenant_id, dedupe_key)
            if existing is not None:
                return existing

        prepared = self.prepare(event_type=event_type, tenant_id=tenant_id, payload=payload)
        delivery = EventDelivery(
            event_id=prepared.event_id,
            event_type=prepared.event_type,
            tenant_id=prepared.tenant_id,
            target_url=target_url,
            body=prepared.body,
            headers=prepared.headers,
            dedupe_key=dedupe_key,
        )
        try:
            saved = self._repo.save(delivery)
        except EventDeliveryConflictError:
            if not dedupe_key:
                raise
            existing = self._repo.get_by_dedupe_key(tenant_id, dedupe_key)
            if existing is None:
                raise
            return existing
        self._publish_stream_event(saved, phase='queued')
        return saved

    def record_attempt(
        self,
        event_id: str,
        *,
        delivered: bool,
        status_code: int | None = None,
        error_message: str | None = None,
        now: datetime | None = None,
        max_attempts: int = 3,
    ) -> EventDelivery:
        if self._repo is None:
            raise RuntimeError('event delivery repository is not configured')
        delivery = self._repo.get(event_id)
        if delivery is None:
            raise KeyError(event_id)

        current_time = self._ensure_utc(now or datetime.now(timezone.utc))
        attempt_no = delivery.attempt_count + 1
        attempt = EventDeliveryAttempt(
            id=None,
            event_id=event_id,
            attempt_no=attempt_no,
            delivered=delivered,
            status_code=status_code,
            error_message=error_message,
            created_at=current_time,
        )
        if delivered:
            status = 'delivered'
            last_error = None
            next_attempt_at = None
            delivered_at = current_time
        else:
            last_error = error_message
            delivered_at = None
            if attempt_no >= max_attempts:
                status = 'failed'
                next_attempt_at = None
            else:
                status = 'retrying'
                next_attempt_at = current_time + timedelta(seconds=self._retry_delay_seconds(attempt_no))
        updated = self._repo.record_attempt(
            event_id=event_id,
            attempt=attempt,
            status=status,
            attempt_count=attempt_no,
            last_error=last_error,
            next_attempt_at=next_attempt_at,
            delivered_at=delivered_at,
        )
        self._publish_stream_event(updated, phase='attempt_recorded')
        return updated

    def list_attempts(self, event_id: str) -> list[EventDeliveryAttempt]:
        if self._repo is None:
            raise RuntimeError('event delivery repository is not configured')
        return self._repo.list_attempts(event_id)

    def list_deliveries(self, limit: int = 50) -> list[EventDelivery]:
        if self._repo is None:
            raise RuntimeError('event delivery repository is not configured')
        return self._repo.list_deliveries(limit=limit)

    def list_deliveries_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> dict:
        rows, total = self._repo.list_deliveries_page(
            page=page,
            page_size=page_size,
            search=search,
            status=status,
        )
        return paginated_result(rows, page=page, page_size=page_size, total=total, search=search, status=status)

    def list_stream_events(self, tenant_id: str | None = None, limit: int = 20) -> list[EventDeliveryStreamEvent]:
        return self._stream_broker.recent_events(tenant_id=tenant_id, limit=limit)

    def deliver_due_webhooks(
        self,
        *,
        now: datetime | None = None,
        limit: int = 20,
        max_attempts: int = 3,
        sender: Callable[[EventDelivery], tuple[int | None, str | None] | OutboundHttpResponse] | None = None,
    ) -> list[EventDelivery]:
        if self._repo is None:
            raise RuntimeError('event delivery repository is not configured')
        current_time = self._ensure_utc(now or datetime.now(timezone.utc))
        due_deliveries = self._repo.list_due(now=current_time, limit=limit)
        send = sender or self._sender
        if send is None:
            raise RuntimeError('event webhook sender is not configured')
        results: list[EventDelivery] = []
        for delivery in due_deliveries:
            status_code: int | None = None
            error_message: str | None = None
            try:
                response = send(delivery)
                if isinstance(response, tuple):
                    status_code, error_message = response
                else:
                    status_code = response.status_code
                    if not 200 <= response.status_code < 300:
                        error_message = response.text or f'HTTP {response.status_code}'
            except Exception as exc:
                error_message = sanitize_error(exc)
            delivered = status_code is not None and 200 <= status_code < 300 and not error_message
            results.append(
                self.record_attempt(
                    delivery.event_id,
                    delivered=delivered,
                    status_code=status_code,
                    error_message=error_message,
                    now=current_time,
                    max_attempts=max_attempts,
                )
            )
        return results

    def _retry_delay_seconds(self, attempt_no: int) -> int:
        return self._retry_base_seconds * (2 ** max(0, attempt_no - 1))

    def _publish_stream_event(self, delivery: EventDelivery, *, phase: str) -> None:
        self._stream_broker.publish(
            EventDeliveryStreamEvent(
                id=f'{delivery.event_id}:{delivery.attempt_count}:{delivery.status}:{phase}',
                event='event.delivery',
                tenant_id=delivery.tenant_id,
                data={
                    'event_id': delivery.event_id,
                    'event_type': delivery.event_type,
                    'tenant_id': delivery.tenant_id,
                    'target_url': delivery.target_url,
                    'dedupe_key': delivery.dedupe_key,
                    'status': delivery.status,
                    'phase': phase,
                    'attempt_count': delivery.attempt_count,
                    'last_error': delivery.last_error,
                    'next_attempt_at': delivery.next_attempt_at.isoformat() if delivery.next_attempt_at is not None else None,
                    'delivered_at': delivery.delivered_at.isoformat() if delivery.delivered_at is not None else None,
                    'created_at': delivery.created_at.isoformat() if delivery.created_at is not None else None,
                },
            )
        )

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
