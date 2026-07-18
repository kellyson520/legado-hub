from __future__ import annotations

import json
import re

from app.domain.entities.source_health import SourceHealthDecision, SourceProbeEvidence


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
                "attempted_keywords": evidence.attempted_keywords,
                "attempts": evidence.attempts,
                "next_probe_after_minutes": self._next_probe_minutes(failure_reason),
            },
        )

    def _failure_reason(self, evidence: SourceProbeEvidence) -> str:
        haystacks = [
            evidence.search.request_preview,
            evidence.search.error_message,
            evidence.toc.request_preview,
            evidence.toc.error_message,
            evidence.content.error_message,
        ]
        for stage in (evidence.search, evidence.toc, evidence.content):
            if stage.detail.get("response_preview"):
                haystacks.append(str(stage.detail["response_preview"]))
            diagnostic_detail = {
                key: stage.detail[key]
                for key in (
                    "js_exec_status",
                    "js_error",
                    "http_status",
                    "http_error",
                    "response_kind",
                    "response_preview",
                )
                if key in stage.detail
            }
            if diagnostic_detail:
                haystacks.append(json.dumps(diagnostic_detail, ensure_ascii=False, default=str))
        merged = " ".join(item for item in haystacks if item)
        lowered = merged.lower()
        details = [stage.detail for stage in (evidence.search, evidence.toc, evidence.content)]
        stage_http_statuses = [
            int(detail["http_status"])
            if str(detail.get("http_status")).lstrip("-").isdigit()
            else None
            for detail in details
        ]
        http_statuses = [status for status in stage_http_statuses if status is not None]

        if any(marker in lowered for marker in ["token=undefined", "token=null", "_token=undefined", "_token=null"]):
            return "token_missing"
        if any(marker in lowered for marker in ["worker_eof", "worker_io_error", "js_runtime_error"]):
            return "js_runtime_failure"
        if "is not defined" in lowered:
            return "helper_missing"
        if "unexpected token '<'" in lowered:
            return "upstream_changed"
        if re.search(r'["\']status["\']\s*:\s*4200\b', lowered):
            return "auth_required"
        if any(marker in lowered for marker in ["just a moment", "cloudflare", "captcha", "access denied"]):
            return "waf_blocked"
        if any(status in {403, 429} for status in http_statuses):
            return "waf_blocked"
        if any(status == 401 for status in http_statuses):
            return "auth_required"
        if "10054" in lowered or "connection reset" in lowered:
            return "waf_blocked"
        if any(status == 0 for status in http_statuses):
            return "network_unreachable"
        if any(marker in lowered for marker in ["cannot connect to host", "network name", "name or service not known"]):
            return "network_unreachable"
        if any(marker in lowered for marker in ["ssl", "tls", "handshake"]):
            return "tls_or_handshake_error"
        if "timeout" in lowered:
            return "timeout"
        if any(status >= 400 for status in http_statuses):
            return "http_status_error"
        if any(
            status is not None
            and status >= 200
            and status < 300
            and str(detail.get("response_kind") or "").lower() == "html"
            and str(detail.get("expected_response_kind") or "").lower() == "json"
            for detail, status in zip(details, stage_http_statuses)
        ):
            return "html_instead_of_json"
        if any(str(detail.get("parse_status") or "").lower() == "empty" for detail in details):
            return "parse_empty"
        if evidence.search.status == "failed" and evidence.search.hit_count == 0 and not merged:
            return "keyword_no_result"
        if evidence.search.status == "failed" and '"http_status": 2' in lowered:
            return "parse_empty"
        if evidence.search.status == "ok" and evidence.toc.status == "failed":
            return "parse_empty"
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
        if failure_reason in {
            "token_missing",
            "auth_required",
            "cookie_required",
            "waf_blocked",
            "timeout",
            "network_unreachable",
            "tls_or_handshake_error",
            "http_status_error",
            "js_runtime_failure",
        }:
            return "blocked"
        if failure_reason in {"helper_missing", "upstream_changed", "invalid_source_rule", "deprecated_source"}:
            return "dead"
        if evidence.search.status == "ok" and (
            evidence.toc.status == "failed" or evidence.content.status == "failed"
        ):
            return "degraded"
        if failure_reason in {"html_instead_of_json", "parse_empty", "keyword_no_result", "unknown_error"}:
            return "degraded"
        return "unknown"

    @staticmethod
    def _confidence(failure_reason: str) -> str:
        if failure_reason in {
            "token_missing",
            "helper_missing",
            "upstream_changed",
            "waf_blocked",
            "network_unreachable",
            "tls_or_handshake_error",
            "js_runtime_failure",
        }:
            return "high"
        if failure_reason in {"timeout", "http_status_error", "html_instead_of_json", "parse_empty", "keyword_no_result"}:
            return "medium"
        return "low"

    @staticmethod
    def _next_probe_minutes(failure_reason: str) -> int:
        if failure_reason in {
            "timeout",
            "waf_blocked",
            "network_unreachable",
            "tls_or_handshake_error",
            "http_status_error",
            "js_runtime_failure",
        }:
            return 60
        if failure_reason in {"token_missing", "auth_required"}:
            return 360
        if failure_reason in {"helper_missing", "upstream_changed", "deprecated_source"}:
            return 1440
        return 15
