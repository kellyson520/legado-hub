from app.core.exceptions import NotFoundException, ValidationException


class SourceAuditWorkflowService:
    """Schedules every candidate version through the same durable audit queue."""

    _ACTIVE_STATUSES = frozenset({"queued", "probing", "reviewing"})

    def __init__(self, runtime_repo, build_service):
        self._runtime = runtime_repo
        self._build = build_service

    def schedule(self, *, version_id: str, actor_id: str, trigger: str) -> dict:
        version = self._runtime.get_version(version_id)
        if version is None:
            raise NotFoundException("source version not found")
        if version.status != "candidate":
            raise ValidationException("only candidate source versions can be audited")

        payload = dict(version.payload)
        audit = dict(payload.get("source_audit") or {})
        if audit.get("status") in self._ACTIVE_STATUSES and audit.get("job_id"):
            return {
                "source_version_id": version.id,
                "status": audit["status"],
                "job_id": audit["job_id"],
            }

        job = self._build.submit_existing_candidate(
            tenant_id=str(actor_id),
            source_version_id=version.id,
            url=version.source_id,
            trigger=trigger,
        )
        audit.update({
            "status": "queued",
            "workflow": "unified",
            "job_id": job.id,
            "trigger": trigger,
            "reason_code": None,
        })
        payload["source_audit"] = audit
        self._runtime.update_version_payload(version.id, payload)
        return {"source_version_id": version.id, "status": "queued", "job_id": job.id}
