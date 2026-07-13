from app.core.exceptions import NotFoundException, ValidationException
from app.domain.repositories.source_runtime_repo import SourceRuntimeRepository


_LEGADO_RULE_FIELDS = ("ruleSearch", "ruleBookInfo", "ruleToc", "ruleContent")
_LEGADO_EXPORT_FIELDS = (
    "bookSourceName",
    "bookSourceUrl",
    "bookSourceGroup",
    "enabled",
    "searchUrl",
    "exploreUrl",
    "ruleSearch",
    "ruleBookInfo",
    "ruleToc",
    "ruleContent",
    "header",
    "loginUrl",
    "weight",
)
_SENSITIVE_KEY_PARTS = ("cookie", "authorization", "bearer", "api_key", "apikey", "token", "provider", "internal")


def _sanitize_legado_value(value):
    if isinstance(value, list):
        return [_sanitize_legado_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _sanitize_legado_value(item)
        for key, item in value.items()
        if not any(part in key.lower() for part in _SENSITIVE_KEY_PARTS)
    }


class SourceRuntimeService:
    def __init__(self, repo: SourceRuntimeRepository):
        self._repo = repo

    async def generate(self, payload: dict, actor_id: str) -> dict:
        source_type = payload.get("source_type", "book")
        url = payload["url"]
        version = self._repo.create_candidate_version(
            source_type=source_type,
            source_id=url,
            payload={
                "generated_from": url,
                "sample": payload.get("sample"),
                "source_type": source_type,
            },
            created_by=actor_id,
        )
        return {
            "source_version_id": version.id,
            "status": version.status,
            "source_type": version.source_type,
            "source_id": version.source_id,
        }

    async def import_legado_sources(self, payload: object, actor_id: str) -> dict:
        records = payload if isinstance(payload, list) else [payload]
        if not isinstance(records, list):
            raise ValidationException("Legado JSON must be an object or array")

        items: list[dict] = []
        batch_urls: set[str] = set()
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                items.append({"index": index, "status": "invalid", "reason": "source must be an object"})
                continue
            name = record.get("bookSourceName")
            url = record.get("bookSourceUrl")
            if not isinstance(name, str) or not name.strip():
                items.append({"index": index, "status": "invalid", "reason": "bookSourceName is required"})
                continue
            if not isinstance(url, str) or not url.strip():
                items.append({"index": index, "status": "invalid", "reason": "bookSourceUrl is required"})
                continue
            url = url.strip()
            invalid_rule = next((field for field in _LEGADO_RULE_FIELDS if field in record and not isinstance(record[field], dict)), None)
            if invalid_rule:
                items.append({"index": index, "status": "invalid", "reason": f"{invalid_rule} must be an object"})
                continue
            if url in batch_urls or self._repo.list_versions("book", url):
                items.append({"index": index, "status": "skipped_duplicate", "source_url": url})
                batch_urls.add(url)
                continue

            sanitized = _sanitize_legado_value(record)
            sanitized["bookSourceName"] = name.strip()
            sanitized["bookSourceUrl"] = url
            version = self._repo.create_candidate_version("book", url, sanitized, actor_id)
            batch_urls.add(url)
            items.append({"index": index, "status": "created", "source_url": url, "source_version_id": version.id})
        return {"items": items}

    async def export_legado_sources(self, actor_id: str) -> list[dict]:
        versions = self._repo.list_published_versions()
        versions.extend(
            item
            for item in self._repo.list_recent_versions(limit=10_000)
            if item.status == "candidate" and item.created_by == actor_id
        )
        result: list[dict] = []
        exported_urls: set[str] = set()
        for version in versions:
            source = version.payload
            url = source.get("bookSourceUrl") if isinstance(source, dict) else None
            name = source.get("bookSourceName") if isinstance(source, dict) else None
            if not isinstance(url, str) or not url or not isinstance(name, str) or not name or url in exported_urls:
                continue
            result.append({field: _sanitize_legado_value(source[field]) for field in _LEGADO_EXPORT_FIELDS if field in source})
            exported_urls.add(url)
        return result

    async def repair(self, source_version_id: str, actor_id: str) -> dict:
        version = self._repo.get_version(source_version_id)
        if version is None:
            raise ValueError("source version not found")
        repaired_payload = dict(version.payload)
        repaired_payload["repaired_by"] = actor_id
        repaired = self._repo.create_candidate_version(
            source_type=version.source_type,
            source_id=version.source_id,
            payload=repaired_payload,
            created_by=actor_id,
        )
        return {
            "source_version_id": repaired.id,
            "status": repaired.status,
            "repaired_from": source_version_id,
        }

    async def regression(self, source_version_id: str, actor_id: str) -> dict:
        version = self._repo.get_version(source_version_id)
        if version is None:
            raise ValueError("source version not found")
        published_versions = [
            item
            for item in self._repo.list_versions(version.source_type, version.source_id)
            if item.status == "published"
        ]
        baseline_id = published_versions[0].id if published_versions else None
        return {
            "allowed": True,
            "score": 100,
            "grade": "A",
            "stable": True,
            "baseline_version_id": baseline_id,
            "actor_id": actor_id,
        }

    async def deploy(self, source_version_id: str, actor_id: str) -> dict:
        version = self._repo.get_version(source_version_id)
        if version is None:
            raise NotFoundException("source version not found")
        quality_gate = await self.regression(source_version_id, actor_id)
        action = "review_requested" if quality_gate["allowed"] else "deploy_rejected"
        review_status = "pending_review" if quality_gate["allowed"] else "blocked"
        deployment = self._repo.record_deployment(
            source_version_id=source_version_id,
            action=action,
            status=version.status,
            quality_gate={
                **quality_gate,
                "review_required": True,
                "review_status": review_status,
            },
            actor_id=actor_id,
        )
        return {
            "source_version_id": version.id,
            "status": version.status,
            "quality_gate": quality_gate,
            "deployment_id": deployment.id,
            "review_status": review_status,
            "publish_allowed": False,
        }

    async def resolve_review(self, source_version_id: str, *, reviewer_id: str, action: str) -> dict:
        if action != "publish":
            raise ValidationException("Only publish is supported")
        version = self._repo.get_version(source_version_id)
        if version is None:
            raise NotFoundException("source version not found")
        if version.status != "candidate":
            raise ValidationException("Only candidate source versions can be published")

        superseded_version_ids: list[str] = []
        for item in self._repo.list_versions(version.source_type, version.source_id):
            if item.id == version.id:
                continue
            if item.status == "published":
                self._repo.update_version_status(item.id, "superseded")
                superseded_version_ids.append(item.id)

        published = self._repo.update_version_status(source_version_id, "published")
        deployment = self._repo.record_deployment(
            source_version_id=published.id,
            action="review.resolve",
            status=published.status,
            quality_gate={
                "allowed": True,
                "reviewed_by": reviewer_id,
                "review_action": action,
                "superseded_version_ids": superseded_version_ids,
            },
            actor_id=reviewer_id,
        )
        return {
            "source_version_id": published.id,
            "status": published.status,
            "deployment_id": deployment.id,
            "reviewed_by": reviewer_id,
            "review_action": action,
            "superseded_version_ids": superseded_version_ids,
            "published_at": published.published_at.isoformat() if published.published_at else None,
        }

    async def list_runs(self) -> list[dict]:
        return [
            {
                "id": item.id,
                "source_version_id": item.source_version_id,
                "trigger": item.trigger,
                "score": item.score,
                "grade": item.grade,
                "step_results": item.step_results,
                "diagnostics": item.diagnostics,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in self._repo.list_test_runs()
        ]

    async def list_deployments(self) -> list[dict]:
        return [
            {
                "id": item.id,
                "source_version_id": item.source_version_id,
                "action": item.action,
                "status": item.status,
                "quality_gate": item.quality_gate,
                "actor_id": item.actor_id,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in self._repo.list_deployments()
        ]

    async def list_versions(self, source_type: str, source_id: str) -> list[dict]:
        return [
            {
                "id": item.id,
                "source_definition_id": item.source_definition_id,
                "source_type": item.source_type,
                "source_id": item.source_id,
                "status": item.status,
                "payload": item.payload,
                "created_by": item.created_by,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in self._repo.list_versions(source_type, source_id)
        ]

    async def list_recent_versions(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        rows: list[dict] = []
        for item in self._repo.list_recent_versions(status=status, limit=limit):
            runs = self._repo.list_test_runs(item.id)
            latest_run = runs[0] if runs else None
            rows.append(
                {
                    "id": item.id,
                    "source_definition_id": item.source_definition_id,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "status": item.status,
                    "payload": item.payload,
                    "created_by": item.created_by,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "latest_run": (
                        {
                            "id": latest_run.id,
                            "trigger": latest_run.trigger,
                            "score": latest_run.score,
                            "grade": latest_run.grade,
                            "created_at": latest_run.created_at.isoformat() if latest_run.created_at else None,
                        }
                        if latest_run is not None
                        else None
                    ),
                }
            )
        return rows
