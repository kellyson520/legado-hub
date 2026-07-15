from app.core.exceptions import NotFoundException, ValidationException
from app.domain.entities.auth import AuditEvent
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
    def __init__(self, repo: SourceRuntimeRepository, audit=None, source_repo=None):
        self._repo = repo
        self._audit = audit
        self._source_repo = source_repo

    async def register_published_book_sources(self, actor_id: str | int = 0) -> int:
        if self._source_repo is None:
            return 0

        sources_by_url: dict[str, dict] = {}
        for version in self._repo.list_published_versions():
            if version.source_type != "book" or not isinstance(version.payload, dict):
                continue
            source = self._legacy_book_source_payload(version.payload)
            if source is None:
                continue
            sources_by_url.setdefault(source["bookSourceUrl"], source)

        if not sources_by_url:
            return 0
        try:
            legacy_actor_id = int(actor_id)
        except (TypeError, ValueError):
            legacy_actor_id = 0
        return await self._source_repo.upsert_runtime_book_sources(
            list(sources_by_url.values()),
            actor_id=legacy_actor_id,
        )

    @staticmethod
    def _legacy_book_source_payload(payload: dict) -> dict | None:
        for candidate in (payload.get("source_rule"), payload):
            source = SourceRuntimeService._normalize_legacy_book_source_payload(candidate)
            if source is not None:
                return source
        return None

    @staticmethod
    def _normalize_legacy_book_source_payload(candidate: object) -> dict | None:
        if not isinstance(candidate, dict):
            return None
        name = candidate.get("bookSourceName")
        url = candidate.get("bookSourceUrl")
        if not isinstance(name, str) or not name.strip() or not isinstance(url, str) or not url.strip():
            return None
        if any(field in candidate and not isinstance(candidate[field], dict) for field in _LEGADO_RULE_FIELDS):
            return None
        source = dict(candidate)
        source["bookSourceName"] = name.strip()
        source["bookSourceUrl"] = url.strip()
        return source

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

    async def get_version_detail(self, source_version_id: str) -> dict:
        version = self._repo.get_version(source_version_id)
        if version is None:
            raise NotFoundException("source version not found")
        runs = self._repo.list_test_runs(source_version_id)
        latest_run = runs[0] if runs else None
        content_status = self._content_status(version.payload, latest_run.step_results if latest_run else None)
        return {
            "source_version_id": version.id,
            "source_type": version.source_type,
            "source_id": version.source_id,
            "status": version.status,
            "payload": _sanitize_legado_value(version.payload),
            "created_by": version.created_by,
            "created_at": version.created_at.isoformat() if version.created_at else None,
            "latest_validation": self._serialize_test_run(latest_run),
            "content_status": content_status,
            "publish_allowed": self._publish_allowed(version.status, latest_run, content_status),
        }

    async def create_rule_draft(self, source_version_id: str, payload: dict, actor_id: str) -> dict:
        version = self._repo.get_version(source_version_id)
        if version is None:
            raise NotFoundException("source version not found")
        if not isinstance(payload, dict):
            raise ValidationException("Rule payload must be an object")

        draft_payload = {**version.payload, **payload}
        self._validate_rule_payload(draft_payload)
        draft = self._repo.create_candidate_version(
            source_type=version.source_type,
            source_id=version.source_id,
            payload=_sanitize_legado_value(draft_payload),
            created_by=actor_id,
        )
        await self._audit_event(actor_id, "source_rule.draft", draft.id)
        return {
            "source_version_id": draft.id,
            "status": draft.status,
            "source_type": draft.source_type,
            "source_id": draft.source_id,
        }

    async def validate_rule_version(self, source_version_id: str, actor_id: str) -> dict:
        version = self._repo.get_version(source_version_id)
        if version is None:
            raise NotFoundException("source version not found")

        content_status = self._content_status(version.payload)
        steps: dict[str, dict] = {}
        diagnostics: list[str] = []
        for field, step_name in (
            ("ruleSearch", "search"),
            ("ruleToc", "toc"),
            ("ruleContent", "content"),
        ):
            rule = version.payload.get(field)
            passed = isinstance(rule, dict) and bool(rule)
            if step_name == "content" and content_status == "verification_wall":
                passed = False
            steps[step_name] = {
                "passed": passed,
                "elapsed_ms": 0,
                "status": content_status if step_name == "content" else ("ready" if passed else "missing_rule"),
            }
            if not passed:
                diagnostics.append(
                    "正文访问受阻，禁止发布"
                    if step_name == "content" and content_status == "verification_wall"
                    else f"{field} is required"
                )

        has_book_info = isinstance(version.payload.get("ruleBookInfo"), dict) and bool(version.payload["ruleBookInfo"])
        steps["book_info"] = {
            "passed": has_book_info,
            "elapsed_ms": 0,
            "status": "ready" if has_book_info else "optional_missing",
        }
        if content_status == "verification_wall" or any(not steps[name]["passed"] for name in ("search", "toc", "content")):
            score, grade = 0, "F"
        elif has_book_info:
            score, grade = 100, "A"
        else:
            score, grade = 85, "B"

        run = self._repo.record_test_run(
            source_version_id=version.id,
            trigger="rule_editor",
            score=score,
            grade=grade,
            step_results=steps,
            diagnostics=diagnostics,
        )
        await self._audit_event(actor_id, "source_rule.validate", version.id)
        return {
            "source_version_id": version.id,
            "validation_id": run.id,
            "score": run.score,
            "grade": run.grade,
            "step_results": run.step_results,
            "diagnostics": run.diagnostics,
            "content_status": content_status,
            "publish_allowed": self._publish_allowed(version.status, run, content_status),
        }

    async def publish_rule_version(self, source_version_id: str, actor_id: str) -> dict:
        version = self._repo.get_version(source_version_id)
        if version is None:
            raise NotFoundException("source version not found")
        if version.status != "candidate":
            raise ValidationException("Only candidate source versions can be published")
        self._assert_source_audit_publishable(version)

        latest_runs = self._repo.list_test_runs(source_version_id)
        latest_run = latest_runs[0] if latest_runs else None
        content_status = self._content_status(version.payload, latest_run.step_results if latest_run else None)
        if content_status == "verification_wall":
            raise ValidationException("verification_wall blocks publication")
        if latest_run is None or latest_run.grade not in {"A", "B"}:
            raise ValidationException("A or B validation grade is required before publication")

        superseded_version_ids: list[str] = []
        for item in self._repo.list_versions(version.source_type, version.source_id):
            if item.id != version.id and item.status == "published":
                self._repo.update_version_status(item.id, "superseded")
                superseded_version_ids.append(item.id)

        published = self._repo.update_version_status(version.id, "published")
        deployment = self._repo.record_deployment(
            source_version_id=published.id,
            action="source_rule.publish",
            status=published.status,
            quality_gate={
                "allowed": True,
                "grade": latest_run.grade,
                "content_status": content_status,
                "superseded_version_ids": superseded_version_ids,
            },
            actor_id=actor_id,
        )
        await self._audit_event(actor_id, "source_rule.publish", published.id)
        await self.register_published_book_sources(actor_id)
        return {
            "source_version_id": published.id,
            "status": published.status,
            "grade": latest_run.grade,
            "content_status": content_status,
            "publish_allowed": True,
            "deployment_id": deployment.id,
            "superseded_version_ids": superseded_version_ids,
            "published_at": published.published_at.isoformat() if published.published_at else None,
        }

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
        self._assert_source_audit_publishable(version)

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
        await self.register_published_book_sources(reviewer_id)
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

    @staticmethod
    def _validate_rule_payload(payload: dict) -> None:
        name = payload.get("bookSourceName")
        url = payload.get("bookSourceUrl")
        if not isinstance(name, str) or not name.strip():
            raise ValidationException("bookSourceName is required")
        if not isinstance(url, str) or not url.strip():
            raise ValidationException("bookSourceUrl is required")
        invalid_field = next(
            (field for field in _LEGADO_RULE_FIELDS if field in payload and not isinstance(payload[field], dict)),
            None,
        )
        if invalid_field:
            raise ValidationException(f"{invalid_field} must be an object")

    @staticmethod
    def _content_status(payload: dict, step_results: dict | None = None) -> str:
        if isinstance(step_results, dict):
            content_step = step_results.get("content")
            if isinstance(content_step, dict) and isinstance(content_step.get("status"), str):
                return content_step["status"]
        if isinstance(payload.get("content_status"), str):
            return payload["content_status"]
        autonomous_build = payload.get("autonomous_build")
        if isinstance(autonomous_build, dict):
            probe = autonomous_build.get("probe")
            if isinstance(probe, dict) and isinstance(probe.get("content_status"), str):
                return probe["content_status"]
        return "ready"

    def _assert_source_audit_publishable(self, version) -> None:
        payload = version.payload if isinstance(version.payload, dict) else {}
        if "source_audit" not in payload:
            return
        audit = payload["source_audit"]
        if not isinstance(audit, dict) or audit.get("status") != "passed":
            raise ValidationException("source audit must pass before publication")
        if audit.get("test_run_pending"):
            raise ValidationException("source audit test-run checkpoint must settle before publication")

    @staticmethod
    def _serialize_test_run(run) -> dict | None:
        if run is None:
            return None
        return {
            "id": run.id,
            "trigger": run.trigger,
            "score": run.score,
            "grade": run.grade,
            "step_results": run.step_results,
            "diagnostics": run.diagnostics,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }

    @staticmethod
    def _publish_allowed(status: str, run, content_status: str) -> bool:
        return status == "candidate" and content_status != "verification_wall" and run is not None and run.grade in {"A", "B"}

    async def _audit_event(self, actor_id: str, action: str, source_version_id: str) -> None:
        if self._audit is None:
            return
        await self._audit.record_audit(
            AuditEvent(
                actor_id=int(actor_id),
                action=action,
                resource="source_rule",
                detail=source_version_id,
            )
        )
