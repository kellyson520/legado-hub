import asyncio
from copy import deepcopy

from app.core.exceptions import NotFoundException, ValidationException
from app.core.pagination import paginated_result
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
    LIVE_PROBE_TRIGGER = "rule_editor_live_probe"
    LIVE_PROBE_TIMEOUT_SECONDS = 25
    _SAFE_PROBE_STATUSES = {"ok", "failed", "skipped", "unknown"}
    _SAFE_PROBE_DETAIL_ENUMS = {
        "response_kind": {"json", "html", "text", "network_error"},
        "expected_response_kind": {"json", "html", "text"},
        "parse_status": {"unknown", "empty", "content_access_blocked"},
        "block_reason": {"verification_wall"},
        "js_exec_status": {"ok", "fail"},
    }

    def __init__(self, repo: SourceRuntimeRepository, audit=None, source_repo=None, source_probe=None, audit_workflow=None):
        self._repo = repo
        self._audit = audit
        self._source_repo = source_repo
        self._source_probe = source_probe
        self._audit_workflow = audit_workflow

    async def aclose(self) -> None:
        close = getattr(self._source_probe, "aclose", None)
        if callable(close):
            await close()

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

        items: list[dict | None] = [None] * len(records)
        batch_urls: set[str] = set()
        candidates: list[tuple[int, str, dict]] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                items[index] = {"index": index, "status": "invalid", "reason": "source must be an object"}
                continue
            name = record.get("bookSourceName")
            url = record.get("bookSourceUrl")
            if not isinstance(name, str) or not name.strip():
                items[index] = {"index": index, "status": "invalid", "reason": "bookSourceName is required"}
                continue
            if not isinstance(url, str) or not url.strip():
                items[index] = {"index": index, "status": "invalid", "reason": "bookSourceUrl is required"}
                continue
            url = url.strip()
            invalid_rule = next((field for field in _LEGADO_RULE_FIELDS if field in record and not isinstance(record[field], dict)), None)
            if invalid_rule:
                items[index] = {"index": index, "status": "invalid", "reason": f"{invalid_rule} must be an object"}
                continue
            if url in batch_urls:
                items[index] = {"index": index, "status": "skipped_duplicate", "source_url": url}
                batch_urls.add(url)
                continue

            sanitized = _sanitize_legado_value(record)
            sanitized["bookSourceName"] = name.strip()
            sanitized["bookSourceUrl"] = url
            batch_urls.add(url)
            candidates.append((index, url, sanitized))

        existing_urls = self._repo.existing_source_ids("book", [url for _index, url, _payload in candidates])
        to_create = [candidate for candidate in candidates if candidate[1] not in existing_urls]
        version_ids = self._repo.create_candidate_version_ids_bulk(
            "book",
            [(url, sanitized, actor_id) for _index, url, sanitized in to_create],
        )
        audit_queued = 0
        if self._audit_workflow is not None:
            for version_id in version_ids.values():
                self._audit_workflow.schedule(
                    version_id=version_id,
                    actor_id=str(actor_id),
                    trigger="import",
                )
                audit_queued += 1
        for index, url, _sanitized in candidates:
            if url in existing_urls:
                items[index] = {"index": index, "status": "skipped_duplicate", "source_url": url}
            else:
                items[index] = {
                    "index": index,
                    "status": "created",
                    "source_url": url,
                    "source_version_id": version_ids[url],
                }
        return {
            "items": [item for item in items if item is not None],
            "audit_queued": audit_queued,
        }

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

    async def list_visible_sources(self, actor_id: str, *, page: int = 1, page_size: int = 20, search: str = "") -> dict:
        visible, total = self._repo.list_visible_versions(
            str(actor_id),
            page=page,
            page_size=page_size,
            search=search,
        )
        rows = []
        for version in visible:
            payload = _sanitize_legado_value(version.payload)
            name = payload.get("bookSourceName", version.source_id)
            url = payload.get("bookSourceUrl", version.source_id)
            rows.append(
                {
                    "id": version.id,
                    "bookSourceName": str(name),
                    "bookSourceUrl": str(url),
                    "bookSourceGroup": str(payload.get("bookSourceGroup") or "default"),
                    "enabled": bool(payload.get("enabled", True)),
                    "sourceStatus": version.status,
                    "sourceOrigin": "runtime_version",
                    "lastCheckTime": (version.published_at or version.created_at).isoformat(),
                    "errorMsg": None,
                }
            )
        return paginated_result(rows, page=page, page_size=page_size, total=total, search=search)

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
            "publish_allowed": self._publish_allowed(version, latest_run, content_status),
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
        steps, diagnostics = self._shape_validation(version.payload, content_status)
        trigger = "rule_editor_shape"

        if self._requires_live_probe(version) and content_status != "verification_wall":
            trigger = self.LIVE_PROBE_TRIGGER
            live_steps, live_diagnostics = await self._run_live_probe(version)
            steps.update(live_steps)
            diagnostics.extend(live_diagnostics)
            content_status = self._content_status(version.payload, steps)

        has_book_info = steps["book_info"]["passed"]
        full_chain_passed = all(steps[name]["passed"] for name in ("search", "toc", "content"))
        if not full_chain_passed:
            score, grade = 0, "F"
        elif has_book_info:
            score, grade = 100, "A"
        else:
            score, grade = 85, "B"

        run = self._repo.record_test_run(
            source_version_id=version.id,
            trigger=trigger,
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
            "publish_allowed": self._publish_allowed(version, run, content_status),
        }

    def _shape_validation(self, payload: dict, content_status: str) -> tuple[dict[str, dict], list[str]]:
        steps: dict[str, dict] = {}
        diagnostics: list[str] = []
        for field, step_name in (
            ("ruleSearch", "search"),
            ("ruleToc", "toc"),
            ("ruleContent", "content"),
        ):
            rule = payload.get(field)
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

        has_book_info = isinstance(payload.get("ruleBookInfo"), dict) and bool(payload["ruleBookInfo"])
        steps["book_info"] = {
            "passed": has_book_info,
            "elapsed_ms": 0,
            "status": "ready" if has_book_info else "optional_missing",
        }
        return steps, diagnostics

    async def _run_live_probe(self, version) -> tuple[dict[str, dict], list[str]]:
        if self._source_probe is None:
            return self._live_probe_unavailable("live probe service is not configured")

        source = self._source_for_live_probe(version)
        if source is None:
            return self._live_probe_unavailable("book source payload is invalid")

        try:
            evidence = await asyncio.wait_for(
                self._source_probe.probe_source(
                    source,
                    keyword_samples=self._probe_keywords(version.payload),
                    probe_mode="full_chain",
                ),
                timeout=self.LIVE_PROBE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return self._live_probe_unavailable("live probe timed out")
        except Exception:
            return self._live_probe_unavailable("live probe failed")

        steps: dict[str, dict] = {}
        diagnostics: list[str] = []
        for stage_name in ("search", "toc", "content"):
            stage = getattr(evidence, stage_name)
            steps[stage_name] = self._safe_live_probe_step(stage)
            passed = steps[stage_name]["passed"]
            if not passed:
                diagnostics.append(self._live_probe_diagnostic(stage_name, steps[stage_name]))
        return steps, diagnostics

    @classmethod
    def _safe_live_probe_step(cls, stage) -> dict:
        status = stage.status if stage.status in cls._SAFE_PROBE_STATUSES else "unknown"
        detail = stage.detail if isinstance(stage.detail, dict) else {}
        step = {
            "passed": status == "ok",
            "elapsed_ms": cls._bounded_non_negative_int(stage.elapsed_ms),
            "status": status,
            "hit_count": cls._bounded_non_negative_int(stage.hit_count),
            "validation_kind": "live_probe",
        }
        for key in ("http_status", "content_length", "http_elapsed_ms"):
            if key in detail:
                step[key] = cls._bounded_non_negative_int(detail[key])
        for key, allowed in cls._SAFE_PROBE_DETAIL_ENUMS.items():
            value = detail.get(key)
            if value in allowed:
                step[key] = value
        return step

    @staticmethod
    def _bounded_non_negative_int(value) -> int:
        try:
            return min(max(int(value), 0), 1_000_000_000)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _source_for_live_probe(version) -> dict | None:
        payload = version.payload if isinstance(version.payload, dict) else {}
        source = SourceRuntimeService._legacy_book_source_payload(payload)
        if source is None:
            return None
        result = deepcopy(source)
        result["id"] = version.id
        return result

    @staticmethod
    def _probe_keywords(payload: dict) -> list[str]:
        keyword = payload.get("keyword") if isinstance(payload, dict) else None
        values = [keyword] if isinstance(keyword, str) and keyword.strip() else []
        values.extend(["斗罗大陆", "捞尸人", "剑来"])
        return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))

    @staticmethod
    def _live_probe_diagnostic(stage_name: str, step: dict) -> str:
        reason = step.get("block_reason")
        return f"live {stage_name} probe failed" + (f" ({reason})" if reason else "")

    @classmethod
    def _live_probe_unavailable(cls, diagnostic: str) -> tuple[dict[str, dict], list[str]]:
        steps = {
            stage: {
                "passed": False,
                "elapsed_ms": 0,
                "status": "not_run",
                "validation_kind": "live_probe",
            }
            for stage in ("search", "toc", "content")
        }
        return steps, [diagnostic]

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
        if not self._publish_allowed(version, latest_run, content_status):
            raise ValidationException("a passing live probe is required before publication")

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
        latest_runs = self._repo.list_test_runs(source_version_id)
        latest_run = latest_runs[0] if latest_runs else None
        content_status = self._content_status(version.payload, latest_run.step_results if latest_run else None)
        if not self._publish_allowed(version, latest_run, content_status):
            raise ValidationException("a passing live probe is required before publication")

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

    async def list_runs_page(self, *, page: int = 1, page_size: int = 50, search: str = "") -> dict:
        rows, total = self._repo.list_test_runs_page(page=page, page_size=page_size, search=search)
        return paginated_result(
            [
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
                for item in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
            search=search,
        )

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

    async def list_deployments_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> dict:
        rows, total = self._repo.list_deployments_page(
            page=page,
            page_size=page_size,
            search=search,
            status=status,
        )
        return paginated_result(
            [
                {
                    "id": item.id,
                    "source_version_id": item.source_version_id,
                    "action": item.action,
                    "status": item.status,
                    "quality_gate": item.quality_gate,
                    "actor_id": item.actor_id,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
            search=search,
            status=status,
        )

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

    async def list_recent_versions(self, *, status: str | list[str] | None = None, limit: int = 50) -> list[dict]:
        rows: list[dict] = []
        versions = self._repo.list_recent_versions(status=status, limit=limit)
        latest_runs = self._repo.list_latest_test_runs([item.id for item in versions])
        for item in versions:
            latest_run = latest_runs.get(item.id)
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

    async def list_recent_versions_page(
        self,
        *,
        status: str | list[str] | None = None,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
    ) -> dict:
        versions, total = self._repo.list_recent_versions_page(
            status=status,
            page=page,
            page_size=page_size,
            search=search,
        )
        latest_runs = self._repo.list_latest_test_runs([item.id for item in versions])
        rows: list[dict] = []
        for item in versions:
            latest_run = latest_runs.get(item.id)
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
        return paginated_result(rows, page=page, page_size=page_size, total=total, search=search, status=status)

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
        audit = payload.get("source_audit")
        if not isinstance(audit, dict):
            raise ValidationException("source audit is missing; queue audit before publication")
        if audit.get("status") not in {"approved_for_publish", "passed"}:
            raise ValidationException("source audit must pass before publication")
        if audit.get("test_run_pending"):
            raise ValidationException("source audit test-run checkpoint must settle before publication")

    @classmethod
    def _serialize_test_run(cls, run) -> dict | None:
        if run is None:
            return None
        return {
            "id": run.id,
            "trigger": run.trigger,
            "score": run.score,
            "grade": run.grade,
            "step_results": cls._safe_serialized_steps(run.step_results),
            "diagnostics": [cls._safe_diagnostic(item) for item in run.diagnostics],
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }

    @classmethod
    def _safe_serialized_steps(cls, step_results: object) -> dict:
        if not isinstance(step_results, dict):
            return {}
        result: dict[str, dict] = {}
        for stage_name, stage in step_results.items():
            if not isinstance(stage, dict):
                continue
            safe = {
                "passed": bool(stage.get("passed")),
                "elapsed_ms": cls._bounded_non_negative_int(stage.get("elapsed_ms")),
                "status": stage.get("status") if stage.get("status") in cls._SAFE_PROBE_STATUSES else "unknown",
            }
            for key in ("hit_count", "http_status", "content_length", "http_elapsed_ms", "attempt"):
                if key in stage:
                    safe[key] = cls._bounded_non_negative_int(stage[key])
            for key, allowed in cls._SAFE_PROBE_DETAIL_ENUMS.items():
                if stage.get(key) in allowed:
                    safe[key] = stage[key]
            if stage.get("validation_kind") == "live_probe":
                safe["validation_kind"] = "live_probe"
            if stage.get("run_kind") in {"normal", "manual_browser"}:
                safe["run_kind"] = stage["run_kind"]
            result[str(stage_name)] = safe
        return result

    @staticmethod
    def _safe_diagnostic(value: object) -> str:
        if not isinstance(value, str):
            return "validation_failed"
        if value in {
            "正文访问受阻，禁止发布",
            "live probe service is not configured",
            "book source payload is invalid",
            "live probe timed out",
            "live probe failed",
            "validation_failed",
        }:
            return str(value)
        if value.startswith("rule") and value.endswith(" is required"):
            return value
        if value.startswith("live ") and " probe failed" in value:
            return value if value.endswith("probe failed") or value.endswith("(verification_wall)") else "validation_failed"
        return "validation_failed"

    @staticmethod
    def _requires_live_probe(version) -> bool:
        return version.source_type == "book"

    @classmethod
    def _publish_allowed(cls, version, run, content_status: str) -> bool:
        if version.status != "candidate" or content_status == "verification_wall" or run is None:
            return False
        if run.grade not in {"A", "B"}:
            return False
        if not cls._requires_live_probe(version):
            return True
        return cls._is_passing_live_probe(run)

    @classmethod
    def _is_passing_live_probe(cls, run) -> bool:
        steps = run.step_results if isinstance(run.step_results, dict) else {}
        if run.trigger == cls.LIVE_PROBE_TRIGGER:
            return all(
                isinstance(steps.get(stage), dict)
                and steps[stage].get("passed") is True
                and steps[stage].get("validation_kind") == "live_probe"
                for stage in ("search", "toc", "content")
            )
        if run.trigger == "source_audit":
            audit = steps.get("source_audit")
            return (
                isinstance(audit, dict)
                and audit.get("passed") is True
                and all(
                    isinstance(steps.get(stage), dict) and steps[stage].get("passed") is True
                    for stage in ("search", "toc", "content")
                )
            )
        return False

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
