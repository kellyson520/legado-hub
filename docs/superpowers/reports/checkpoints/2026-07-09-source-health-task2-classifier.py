from __future__ import annotations

from app.application.services.source_health_models import SourceHealthDecision, SourceProbeEvidence


class SourceHealthClassifierService:
    def classify(self, evidence: SourceProbeEvidence) -> SourceHealthDecision:
        failure_reason = self._failure_reason(evidence)
        health_status = self._health_status(evidence, failure_reason)
        route_policy = "allow"
        route_score = 100.0
        if health_status == "degraded":
            route_policy = "deprioritize"
            route_score = 45.0
        elif health_status in {"blocked", "dead"}:
            route_policy = "skip"
            route_score = 0.0
        elif health_status == "unknown":
            route_policy = "probe_only"
            route_score = 10.0

        return SourceHealthDecision(
            source_id=evidence.source_id,
            source_name=evidence.source_name,
            source_url=evidence.source_url,
            health_status=health_status,
            search_status=evidence.search.status,
            toc_status=evidence.toc.status,
            content_status=evidence.content.status,
            failure_reason=failure_reason,
            decision_confidence=self._confidence(failure_reason),
            route_policy=route_policy,
            route_score=route_score,
            metadata={
                "keyword": evidence.keyword,
                "next_probe_after_minutes": self._next_probe_minutes(failure_reason),
            },
        )

    def _failure_reason(self, evidence: SourceProbeEvidence) -> str:
        haystacks = [
            evidence.search.request_preview,
            evidence.search.error_message,
            evidence.content.error_message,
            str(evidence.search.detail),
            str(evidence.content.detail),
        ]
        merged = " ".join(item for item in haystacks if item)
        lowered = merged.lower()

        if "token=undefined" in lowered:
            return "token_missing"
        if "is not defined" in lowered:
            return "helper_missing"
        if "unexpected token '<'" in lowered:
            return "upstream_changed"
        if "10054" in lowered or "connection reset" in lowered:
            return "waf_blocked"
        if "timeout" in lowered:
            return "timeout"
        if evidence.search.status == "failed" and evidence.search.hit_count == 0 and not merged:
            return "keyword_no_result"
        if evidence.search.status == "ok" and evidence.toc.status == "ok" and evidence.content.status == "failed":
            return "parse_empty"
        if any(stage.status == "failed" for stage in [evidence.search, evidence.toc, evidence.content]):
            return "unknown_error"
        return ""

    @staticmethod
    def _health_status(evidence: SourceProbeEvidence, failure_reason: str) -> str:
        if (
            evidence.search.status == "ok"
            and evidence.toc.status in {"ok", "skipped"}
            and evidence.content.status in {"ok", "skipped"}
        ):
            return "healthy"
        if failure_reason in {"token_missing", "auth_required", "cookie_required", "waf_blocked", "timeout"}:
            return "blocked"
        if failure_reason in {"helper_missing", "upstream_changed", "invalid_source_rule", "deprecated_source"}:
            return "dead"
        if evidence.search.status == "ok" and (
            evidence.toc.status == "failed" or evidence.content.status == "failed"
        ):
            return "degraded"
        return "unknown"

    @staticmethod
    def _confidence(failure_reason: str) -> str:
        if failure_reason in {"token_missing", "helper_missing", "upstream_changed", "waf_blocked"}:
            return "high"
        if failure_reason in {"timeout", "parse_empty", "keyword_no_result"}:
            return "medium"
        return "low"

    @staticmethod
    def _next_probe_minutes(failure_reason: str) -> int:
        if failure_reason in {"timeout", "waf_blocked"}:
            return 60
        if failure_reason in {"token_missing", "auth_required"}:
            return 360
        if failure_reason in {"helper_missing", "upstream_changed", "deprecated_source"}:
            return 1440
        return 15
