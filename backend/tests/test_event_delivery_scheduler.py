import pytest


@pytest.mark.asyncio
async def test_run_event_delivery_job_dispatches_due_webhooks(monkeypatch):
    from app.tasks import scheduler

    class FakeEventDeliveryService:
        def deliver_due_webhooks(self, *, limit=20):
            assert limit == 5
            return [
                type(
                    'Delivery',
                    (),
                    {
                        'event_id': 'evt-1',
                        'status': 'delivered',
                        'attempt_count': 1,
                        'tenant_id': 'tenant-1',
                    },
                )()
            ]

    monkeypatch.setattr(scheduler, 'build_event_delivery_service', lambda: FakeEventDeliveryService())

    result = await scheduler.run_event_delivery_job(limit=5)

    assert result['processed'] == 1
    assert result['deliveries'][0]['event_id'] == 'evt-1'
    assert result['deliveries'][0]['status'] == 'delivered'
