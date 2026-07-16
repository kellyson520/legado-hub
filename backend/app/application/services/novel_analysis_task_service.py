from uuid import uuid4

from app.domain.entities.novel_analysis_task import NovelAnalysisTask


class NovelAnalysisTaskService:
    def __init__(self, repo):
        self._repo = repo

    def create_task(self, work_id: str, tenant_id: str, goal: str, policy: dict | None = None) -> NovelAnalysisTask:
        normalized_policy = dict(policy or {})
        normalized_policy["max_tool_calls_per_task"] = min(max(int(normalized_policy.get("max_tool_calls_per_task", 24)), 1), 100)
        return self._repo.create(NovelAnalysisTask(
            id=uuid4().hex,
            work_id=work_id,
            tenant_id=tenant_id,
            goal=goal,
            policy=normalized_policy,
            checkpoint={"selected_evidence_ids": []},
        ))

    def get_task(self, task_id: str, *, tenant_id: str) -> NovelAnalysisTask | None:
        return self._repo.get(task_id, tenant_id)

    def record_tool_progress(self, task_id: str, evidence_ids: list[str], *, tenant_id: str = "tenant-1") -> NovelAnalysisTask:
        task = self._require(task_id, tenant_id)
        selected = list(task.checkpoint.get("selected_evidence_ids", []))
        for evidence_id in evidence_ids:
            if evidence_id not in selected:
                selected.append(evidence_id)
        count = task.tool_call_count + 1
        status = "paused" if count >= task.policy["max_tool_calls_per_task"] else "running"
        return self._repo.update(NovelAnalysisTask(
            **{**task.__dict__, "status": status, "tool_call_count": count, "checkpoint": {"selected_evidence_ids": selected}},
        ))

    def pause(self, task_id: str, *, tenant_id: str) -> NovelAnalysisTask:
        task = self._require(task_id, tenant_id)
        return self._repo.update(NovelAnalysisTask(**{**task.__dict__, "status": "paused"}))

    def resume(self, task_id: str, *, tenant_id: str) -> NovelAnalysisTask:
        task = self._require(task_id, tenant_id)
        if task.status != "paused":
            raise ValueError("only paused tasks can resume")
        return self._repo.update(NovelAnalysisTask(**{**task.__dict__, "status": "queued"}))

    def _require(self, task_id: str, tenant_id: str) -> NovelAnalysisTask:
        task = self.get_task(task_id, tenant_id=tenant_id)
        if task is None:
            raise LookupError("analysis task not found")
        return task
