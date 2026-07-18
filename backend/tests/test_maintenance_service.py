import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_maintenance_service_resets_enabled_key_quotas():
    from app.application.services.maintenance_service import MaintenanceService

    auth = SimpleNamespace(list_enabled_api_keys=AsyncMock(return_value=[SimpleNamespace(id=7)]))
    store = SimpleNamespace(reset_quota=AsyncMock(), get_quota=AsyncMock())
    service = MaintenanceService(
        source_repo=SimpleNamespace(),
        auth_repo=auth,
        quota_repo=SimpleNamespace(),
        quota_store=store,
    )

    assert await service.reset_daily_quotas() == 1
    assert store.reset_quota.await_count == 3
    assert {call.args[1] for call in store.reset_quota.await_args_list} == {
        "fetch_count",
        "ai_chars",
        "storage_mb",
    }


@pytest.mark.asyncio
async def test_maintenance_service_syncs_only_nonzero_usage():
    from app.application.services.maintenance_service import MaintenanceService

    auth = SimpleNamespace(
        list_enabled_api_keys=AsyncMock(
            return_value=[SimpleNamespace(id=7), SimpleNamespace(id=8)],
        )
    )
    store = SimpleNamespace(
        get_quota=AsyncMock(
            side_effect=[10, 20, 1.5, 0, 0, 0],
        )
    )
    quota_repo = SimpleNamespace(upsert_max_usage=AsyncMock())
    service = MaintenanceService(
        source_repo=SimpleNamespace(),
        auth_repo=auth,
        quota_repo=quota_repo,
        quota_store=store,
    )

    assert await service.sync_quotas(date="2026-07-19") == 1
    quota_repo.upsert_max_usage.assert_awaited_once_with(
        api_key_id=7,
        date="2026-07-19",
        fetch_count=10,
        ai_chars=20,
        storage_mb=1.5,
    )
