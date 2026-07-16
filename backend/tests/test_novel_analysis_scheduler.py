from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_novel_analysis_scheduler_does_not_lease_when_automation_is_paused():
    from app.tasks.scheduler import job_process_novel_analysis_tasks

    class Settings:
        def get_section(self, domain, tab):
            assert (domain, tab) == ("agents", "automation")
            return {"value": {"enabled": True, "background_incremental_enabled": True, "emergency_pause": True}}

    class Tasks:
        def __init__(self):
            self.lease_calls = 0

        def lease_next(self):
            self.lease_calls += 1
            return None

    tasks = Tasks()
    with (
        patch("app.tasks.scheduler.build_system_settings_service", return_value=Settings()),
        patch("app.tasks.scheduler.build_novel_analysis_task_service", return_value=tasks),
        patch("app.tasks.scheduler.build_novel_analysis_pipeline_service"),
    ):
        job_process_novel_analysis_tasks()

    assert tasks.lease_calls == 0


@pytest.mark.asyncio
async def test_novel_analysis_scheduler_leases_once_and_checkpoints_completed_task():
    from app.domain.entities.novel_analysis_task import TaskProcessingResult
    from app.tasks.scheduler import job_process_novel_analysis_tasks

    task = SimpleNamespace(id="task-1", tenant_id="tenant-1")

    class Settings:
        def get_section(self, domain, tab):
            values = {
                "automation": {"enabled": True, "background_incremental_enabled": True, "emergency_pause": False},
                "budgets": {"max_concurrent_tasks": 1},
            }
            return {"value": values[tab]}

    class Tasks:
        def __init__(self):
            self.available = [task, None]
            self.completed = []
            self.blocked = []

        def lease_next(self):
            return self.available.pop(0)

        def complete(self, task_id, *, tenant_id, result):
            self.completed.append((task_id, tenant_id, result))

        def block(self, task_id, *, tenant_id, reason):
            self.blocked.append((task_id, tenant_id, reason))

    class Pipeline:
        def __init__(self):
            self.tasks = []

        async def process_task(self, leased_task, *, tenant_id):
            self.tasks.append((leased_task.id, tenant_id))
            return TaskProcessingResult(claim_ids=("claim-1",), token_count=21)

    tasks = Tasks()
    pipeline = Pipeline()
    with (
        patch("app.tasks.scheduler.build_system_settings_service", return_value=Settings()),
        patch("app.tasks.scheduler.build_novel_analysis_task_service", return_value=tasks),
        patch("app.tasks.scheduler.build_novel_analysis_pipeline_service", return_value=pipeline),
    ):
        job_process_novel_analysis_tasks()

    assert pipeline.tasks == [("task-1", "tenant-1")]
    assert tasks.completed == [("task-1", "tenant-1", TaskProcessingResult(claim_ids=("claim-1",), token_count=21))]
    assert tasks.blocked == []
