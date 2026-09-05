from uuid import uuid4

from app.domain.entities.novel_analysis_task import NovelAnalysisTask, TaskProcessingResult


class NovelAnalysisTaskService:
    def __init__(self, repo):
        self._repo = repo

    def create_task(
        self,
        work_id: str,
        tenant_id: str,
        goal: str,
        policy: dict | None = None,
        *,
        selected_evidence_ids: list[str] | None = None,
    ) -> NovelAnalysisTask:
        normalized_policy = dict(policy or {})
        normalized_policy["max_tool_calls_per_task"] = min(max(int(normalized_policy.get("max_tool_calls_per_task", 24)), 1), 100)
        normalized_policy["max_tokens_per_task"] = min(max(int(normalized_policy.get("max_tokens_per_task", 24000)), 1000), 200000)
        normalized_policy["max_chapters_per_task"] = min(max(int(normalized_policy.get("max_chapters_per_task", 12)), 1), 50)
        selected = list(dict.fromkeys(
            str(evidence_id).strip()
            for evidence_id in (selected_evidence_ids or [])
            if str(evidence_id).strip()
        ))
        return self._repo.create(NovelAnalysisTask(
            id=uuid4().hex,
            work_id=work_id,
            tenant_id=tenant_id,
            goal=goal,
            policy=normalized_policy,
            checkpoint={"selected_evidence_ids": selected},
        ))

    def get_task(self, task_id: str, *, tenant_id: str) -> NovelAnalysisTask | None:
        return self._repo.get(task_id, tenant_id)

    def list_for_work(self, work_id: str, *, tenant_id: str) -> list[NovelAnalysisTask]:
        return self._repo.list_for_work(work_id, tenant_id)

    def queue_reaudit(self, *, claim, tenant_id: str, policy: dict | None = None) -> NovelAnalysisTask:
        task = self.create_task(
            claim.work_id,
            tenant_id,
            f"复审因内容变更而受影响的声明 {claim.id}",
            policy,
            selected_evidence_ids=list(claim.evidence_ids),
        )
        checkpoint = {**task.checkpoint, "reaudit_claim_ids": [claim.id]}
        return self._repo.update(NovelAnalysisTask(**{**task.__dict__, "checkpoint": checkpoint}))

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

    def lease_next(self) -> NovelAnalysisTask | None:
        return self._repo.lease_next()

    def lease(self, task_id: str, *, tenant_id: str) -> NovelAnalysisTask:
        task = self._repo.lease(task_id, tenant_id)
        if task is None:
            raise ValueError("only queued tasks can be run")
        return task

    def complete(
        self,
        task_id: str,
        *,
        tenant_id: str,
        result: TaskProcessingResult,
    ) -> NovelAnalysisTask:
        task = self._require(task_id, tenant_id)
        checkpoint = {
            **task.checkpoint,
            "claim_ids": list(result.claim_ids),
            "token_count": result.token_count,
            "completion_reasons": list(result.reasons),
            "outcomes": [
                {
                    "claim_id": claim_id,
                    "verdict": outcome.verdict,
                    "claim_status": outcome.claim_status,
                    "reasons": list(outcome.reasons),
                }
                for claim_id, outcome in zip(result.claim_ids, result.outcomes)
            ],
        }
        return self._repo.update(NovelAnalysisTask(
            **{**task.__dict__, "status": "completed", "checkpoint": checkpoint},
        ))

    def block(self, task_id: str, *, tenant_id: str, reason: str) -> NovelAnalysisTask:
        task = self._require(task_id, tenant_id)
        checkpoint = {**task.checkpoint, "blocked_reason": str(reason)[:500]}
        return self._repo.update(NovelAnalysisTask(
            **{**task.__dict__, "status": "blocked", "checkpoint": checkpoint},
        ))

    def _require(self, task_id: str, tenant_id: str) -> NovelAnalysisTask:
        task = self.get_task(task_id, tenant_id=tenant_id)
        if task is None:
            raise LookupError("analysis task not found")
        return task
