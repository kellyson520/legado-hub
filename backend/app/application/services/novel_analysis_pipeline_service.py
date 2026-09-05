import json

from app.application.services.novel_analysis_prompts import ROLE_PROMPTS
from app.domain.entities.novel_analysis_task import AdjudicationOutcome, TaskProcessingResult


def select_analysis_evidence(report, *, max_chapters: int, max_spans: int) -> list[dict]:
    max_chapters = max(0, int(max_chapters))
    max_spans = max(0, int(max_spans))
    if max_chapters == 0 or max_spans == 0:
        return []
    candidates: list[tuple[int, dict]] = []
    for kind, items in (("character", report.characters), ("time", report.time_mentions), ("event", report.events)):
        for item in items:
            for evidence in item.evidence:
                evidence_id = f"{evidence.chapter_id}:{evidence.start_offset}:{evidence.end_offset}:{kind}"
                candidates.append((evidence.start_offset, {
                    "evidence_id": evidence_id,
                    "chapter_id": evidence.chapter_id,
                    "start_offset": evidence.start_offset,
                    "end_offset": evidence.end_offset,
                    "excerpt": evidence.text,
                    "kind": kind,
                }))
    selected: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    chapters: set[str] = set()
    for _, item in sorted(candidates, key=lambda value: value[0]):
        key = (item["chapter_id"], item["start_offset"], item["end_offset"])
        if key in seen or (item["chapter_id"] not in chapters and len(chapters) >= max_chapters):
            continue
        seen.add(key)
        chapters.add(item["chapter_id"])
        selected.append(item)
        if len(selected) >= max_spans:
            break
    return selected


ROLE_GROUPS = {
    "extractor": "novel_extract",
    "verifier": "novel_verify",
    "adjudicator": "novel_adjudicate",
    "auditor": "novel_audit",
}


class NovelAnalysisPipelineService:
    _PROMPT_VERSION = "evidence-first-v1"

    def __init__(
        self,
        *,
        knowledge_service,
        evidence_service=None,
        platform=None,
        settings_service=None,
        decision_recorder=None,
    ):
        self._knowledge_service = knowledge_service
        self._evidence_service = evidence_service
        self._platform = platform
        self._settings_service = settings_service
        self._decision_recorder = decision_recorder

    async def process_task(self, task, *, tenant_id: str) -> TaskProcessingResult:
        """Extract candidate claims from selected spans, then independently verify and adjudicate."""
        if task.tenant_id != tenant_id:
            raise PermissionError("analysis task is outside the current tenant")
        if self._platform is None or self._evidence_service is None:
            raise RuntimeError("analysis model runtime is not configured")

        reaudit_claim_ids = task.checkpoint.get("reaudit_claim_ids", [])
        if isinstance(reaudit_claim_ids, list) and reaudit_claim_ids:
            return await self._process_reaudit_task(
                task,
                tenant_id=tenant_id,
                token_budget=self._token_budget(task),
            )

        evidence = self._load_verified_evidence(
            task.checkpoint.get("selected_evidence_ids", []),
        )
        if not evidence:
            return TaskProcessingResult(reasons=("task has no verified selected evidence",))

        snapshot = self._knowledge_service.build_work_snapshot(task.work_id, chapter_limit=8)
        budget = self._token_budget(task)
        extraction, token_count = await self._invoke_role(
            role="extractor",
            tenant_id=tenant_id,
            payload={
                "task_goal": task.goal,
                "work_snapshot": snapshot,
                "evidence": evidence,
            },
            token_count=0,
            token_budget=budget,
        )
        candidates = self._parse_extraction(
            extraction,
            selected_evidence_ids={item["evidence_id"] for item in evidence},
        )
        claim_ids: list[str] = []
        outcomes: list[AdjudicationOutcome] = []
        for candidate in candidates:
            claim = self._knowledge_service.create_claim(work_id=task.work_id, **candidate)
            claim_ids.append(claim.id)
            outcome, token_count = await self._process_claim(
                claim,
                tenant_id=tenant_id,
                token_count=token_count,
                token_budget=budget,
                task_id=task.id,
                task_policy=task.policy,
            )
            outcomes.append(outcome)
        return TaskProcessingResult(
            claim_ids=tuple(claim_ids),
            outcomes=tuple(outcomes),
            token_count=token_count,
        )

    async def _process_reaudit_task(self, task, *, tenant_id: str, token_budget: int) -> TaskProcessingResult:
        claim_ids: list[str] = []
        outcomes: list[AdjudicationOutcome] = []
        token_count = 0
        for claim_id in task.checkpoint.get("reaudit_claim_ids", []):
            claim = self._knowledge_service.get_claim(str(claim_id))
            if claim is None:
                continue
            claim_ids.append(claim.id)
            evidence = self._load_verified_evidence(claim.evidence_ids)
            if len(evidence) != len(dict.fromkeys(claim.evidence_ids)):
                reason = "claim evidence changed or is no longer verified"
                self._record_decision(
                    claim=claim,
                    tenant_id=tenant_id,
                    role="auditor",
                    verdict="human_review",
                    reason=reason,
                    evidence=evidence,
                    invocation={"_invocation": {"provider_group": self._route_group("auditor")}},
                    task_id=task.id,
                    task_policy=task.policy,
                )
                outcomes.append(AdjudicationOutcome("human_review", "candidate", (reason,)))
                continue
            audit, token_count = await self._invoke_role(
                role="auditor",
                tenant_id=tenant_id,
                payload={
                    "task_goal": task.goal,
                    "claim": self._claim_payload(claim),
                    "evidence": evidence,
                },
                token_count=token_count,
                token_budget=token_budget,
            )
            audit_verdict = str(audit.get("verdict") or "").strip().lower()
            audit_reason = self._reason_from(audit, "audit requires human review")
            self._record_decision(
                claim=claim,
                tenant_id=tenant_id,
                role="auditor",
                verdict=audit_verdict or "invalid",
                reason=audit_reason,
                evidence=evidence,
                invocation=audit,
                task_id=task.id,
                task_policy=task.policy,
            )
            if audit_verdict not in {"reaffirm", "pass", "verified", "approve"}:
                outcomes.append(AdjudicationOutcome("human_review", "candidate", (audit_reason,)))
                continue
            outcome, token_count = await self._process_claim(
                claim,
                tenant_id=tenant_id,
                token_count=token_count,
                token_budget=token_budget,
                task_id=task.id,
                task_policy=task.policy,
            )
            outcomes.append(outcome)
        return TaskProcessingResult(
            claim_ids=tuple(claim_ids),
            outcomes=tuple(outcomes),
            token_count=token_count,
        )

    async def process_claim(self, claim_id: str, *, tenant_id: str) -> AdjudicationOutcome:
        claim = self._knowledge_service.get_claim(claim_id)
        if claim is None:
            raise LookupError("knowledge claim not found")
        if self._platform is not None and self._evidence_service is not None:
            outcome, _ = await self._process_claim(
                claim,
                tenant_id=tenant_id,
                token_count=0,
                token_budget=200000,
                task_id=None,
                task_policy=None,
            )
            return outcome
        if claim.epistemic == "speculative":
            return AdjudicationOutcome("human_review", "candidate", ("speculative claim",))
        if claim.predicate in {"same_identity_as", "identity_merge", "retcon"}:
            return AdjudicationOutcome("human_review", "candidate", ("identity or retcon escalation",))
        return AdjudicationOutcome("candidate", "candidate", ("awaiting independent verification",))

    async def _process_claim(
        self,
        claim,
        *,
        tenant_id: str,
        token_count: int,
        token_budget: int,
        task_id: str | None,
        task_policy: dict | None,
    ) -> tuple[AdjudicationOutcome, int]:
        evidence = self._load_verified_evidence(claim.evidence_ids)
        if len(evidence) != len(dict.fromkeys(claim.evidence_ids)):
            return AdjudicationOutcome("reject", "candidate", ("evidence is no longer verified",)), token_count

        claim_payload = self._claim_payload(claim)
        verification, token_count = await self._invoke_role(
            role="verifier",
            tenant_id=tenant_id,
            payload={"claim": claim_payload, "evidence": evidence},
            token_count=token_count,
            token_budget=token_budget,
        )
        verification_verdict = str(verification.get("verdict") or "").strip().lower()
        verification_reason = self._reason_from(verification, "verification did not pass")
        self._record_decision(
            claim=claim,
            tenant_id=tenant_id,
            role="verifier",
            verdict=verification_verdict or "invalid",
            reason=verification_reason,
            evidence=evidence,
            invocation=verification,
            task_id=task_id,
            task_policy=task_policy,
        )
        if verification_verdict not in {"pass", "verified", "approve"}:
            return AdjudicationOutcome("reject", "candidate", (verification_reason,)), token_count

        adjudication, token_count = await self._invoke_role(
            role="adjudicator",
            tenant_id=tenant_id,
            payload={"claim": claim_payload, "evidence": evidence},
            token_count=token_count,
            token_budget=token_budget,
        )
        adjudication_verdict = str(adjudication.get("verdict") or "").strip().lower()
        adjudication_reason = self._reason_from(adjudication, "adjudication did not publish")
        self._record_decision(
            claim=claim,
            tenant_id=tenant_id,
            role="adjudicator",
            verdict=adjudication_verdict or "invalid",
            reason=adjudication_reason,
            evidence=evidence,
            invocation=adjudication,
            task_id=task_id,
            task_policy=task_policy,
        )

        escalation = self._escalation_reason(claim)
        if escalation:
            return AdjudicationOutcome("human_review", "candidate", (escalation,)), token_count
        if self._knowledge_service.detect_conflicts(claim.id) is not None:
            return AdjudicationOutcome("human_review", "candidate", ("live evidence conflict",)), token_count
        if adjudication_verdict not in {"publish", "approve", "pass"}:
            return AdjudicationOutcome("candidate", "candidate", (adjudication_reason,)), token_count
        allowed, reason = self._automatic_publication_allowed(claim)
        if not allowed:
            return AdjudicationOutcome("candidate", "candidate", (reason,)), token_count
        self._knowledge_service.publish_claim(claim.id, actor_id="novel-adjudicator")
        return AdjudicationOutcome("publish", "published", (adjudication_reason,)), token_count

    async def _invoke_role(
        self,
        *,
        role: str,
        tenant_id: str,
        payload: dict,
        token_count: int,
        token_budget: int,
    ) -> tuple[dict, int]:
        request_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        estimated_tokens = max(1, len(request_text) // 4)
        if token_count + estimated_tokens > token_budget:
            raise RuntimeError("analysis task token budget exhausted")
        invocation = await self._platform.invoke_chat(
            provider_group=self._route_group(role),
            model=None,
            payload={
                "temperature": 0,
                "max_tokens": 1200,
                "messages": [
                    {
                        "role": "system",
                        "content": f"{ROLE_PROMPTS[role]} Respond with one JSON object and no markdown.",
                    },
                    {"role": "user", "content": request_text},
                ],
            },
            quota_scope=("tenant", tenant_id),
        )
        text = self._invocation_text(invocation)
        parsed = self._parse_json(text)
        usage = invocation.get("usage") if isinstance(invocation, dict) else None
        used = int(usage.get("total_tokens") or 0) if isinstance(usage, dict) else 0
        return {**parsed, "_invocation": self._invocation_metadata(invocation)}, token_count + used

    def _load_verified_evidence(self, evidence_ids) -> list[dict]:
        if self._evidence_service is None:
            return []
        spans: list[dict] = []
        for evidence_id in dict.fromkeys(str(item) for item in evidence_ids if str(item)):
            span = self._evidence_service.get_verified_span(evidence_id)
            if span is None:
                continue
            spans.append(
                {
                    "evidence_id": span.id,
                    "canonical_chapter_id": span.canonical_chapter_id,
                    "start_offset": span.start_offset,
                    "end_offset": span.end_offset,
                    "excerpt": span.excerpt,
                    "excerpt_sha256": span.excerpt_sha256,
                    "content_sha256": span.content_sha256,
                }
            )
        return spans

    @staticmethod
    def _parse_extraction(payload: dict, *, selected_evidence_ids: set[str]) -> list[dict]:
        raw_claims = payload.get("claims")
        if not isinstance(raw_claims, list):
            raise ValueError("extractor response must contain a claims array")
        candidates: list[dict] = []
        for item in raw_claims[:12]:
            if not isinstance(item, dict):
                continue
            subject = str(item.get("subject_entity_id") or "").strip()
            predicate = str(item.get("predicate") or "").strip()
            evidence_ids = item.get("evidence_ids")
            if not subject or not predicate or not isinstance(evidence_ids, list):
                continue
            normalized_evidence = [str(value) for value in evidence_ids if str(value) in selected_evidence_ids]
            if not normalized_evidence or len(normalized_evidence) != len(evidence_ids):
                continue
            epistemic = str(item.get("epistemic") or "explicit").strip().lower()
            if epistemic not in {"explicit", "inferred", "speculative"}:
                continue
            candidates.append(
                {
                    "subject_entity_id": subject,
                    "predicate": predicate,
                    "object_entity_id": (
                        str(item["object_entity_id"]).strip()
                        if item.get("object_entity_id") is not None
                        else None
                    ),
                    "scalar_value": item.get("scalar_value"),
                    "epistemic": epistemic,
                    "evidence_ids": list(dict.fromkeys(normalized_evidence)),
                }
            )
        return candidates

    def _automatic_publication_allowed(self, claim) -> tuple[bool, str]:
        publishability = self._knowledge_service.publishability(claim.id)
        if not publishability.allowed:
            return False, "; ".join(publishability.reasons) or "claim is not publishable"
        governance = self._settings_value("governance")
        if claim.epistemic == "explicit" and not bool(governance.get("automatic_publish_explicit", True)):
            return False, "automatic publication is disabled for explicit claims"
        if claim.epistemic == "inferred":
            if not bool(governance.get("automatic_publish_inferred", False)):
                return False, "automatic publication is disabled for inferred claims"
            minimum = int(governance.get("minimum_inferred_evidence", 2))
            if len(set(claim.evidence_ids)) < minimum:
                return False, f"inferred claims require {minimum} independent evidence spans"
        return True, ""

    def _route_group(self, role: str) -> str:
        return str(self._settings_value("roles").get(f"{role}_route_group") or ROLE_GROUPS[role])

    def _settings_value(self, tab: str) -> dict:
        if self._settings_service is None:
            return {}
        section = self._settings_service.get_section("agents", tab)
        value = section.get("value") if isinstance(section, dict) else None
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _token_budget(task) -> int:
        try:
            return min(max(int(task.policy.get("max_tokens_per_task", 24000)), 1000), 200000)
        except (AttributeError, TypeError, ValueError):
            return 24000

    @staticmethod
    def _claim_payload(claim) -> dict:
        return {
            "claim_id": claim.id,
            "subject_entity_id": claim.subject_entity_id,
            "predicate": claim.predicate,
            "object_entity_id": claim.object_entity_id,
            "scalar_value": claim.scalar_value,
            "epistemic": claim.epistemic,
            "evidence_ids": list(claim.evidence_ids),
        }

    @staticmethod
    def _parse_json(text: str) -> dict:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.split("\n", 1)[-1]
            if candidate.rstrip().endswith("```"):
                candidate = candidate.rstrip()[:-3]
        value = json.loads(candidate)
        if not isinstance(value, dict):
            raise ValueError("model response must be a JSON object")
        return value

    @staticmethod
    def _invocation_text(invocation) -> str:
        output = invocation.get("output") if isinstance(invocation, dict) else None
        if isinstance(output, dict):
            return str(output.get("text") or "")
        return str(output or "")

    @staticmethod
    def _invocation_metadata(invocation) -> dict:
        if not isinstance(invocation, dict):
            return {}
        return {
            "provider_group": invocation.get("provider_group"),
            "provider_name": invocation.get("provider_name"),
            "model": invocation.get("model"),
        }

    @staticmethod
    def _reason_from(payload: dict, fallback: str) -> str:
        return str(payload.get("reason") or payload.get("summary") or fallback).strip()[:500]

    @staticmethod
    def _escalation_reason(claim) -> str | None:
        if claim.epistemic == "speculative":
            return "speculative claim"
        if claim.predicate in {"same_identity_as", "identity_merge", "retcon"}:
            return "identity or retcon escalation"
        return None

    def _record_decision(
        self,
        *,
        claim,
        tenant_id: str,
        role: str,
        verdict: str,
        reason: str,
        evidence: list[dict],
        invocation: dict,
        task_id: str | None,
        task_policy: dict | None,
    ) -> None:
        recorder = self._decision_recorder
        if recorder is None or not hasattr(recorder, "record_adjudication"):
            return
        metadata = invocation.get("_invocation", {})
        recorder.record_adjudication(
            claim_id=claim.id,
            tenant_id=tenant_id,
            role=role,
            verdict=verdict,
            reasons=(reason,),
            evidence_ids=[item["evidence_id"] for item in evidence],
            provider_group=metadata.get("provider_group"),
            provider_name=metadata.get("provider_name"),
            model=metadata.get("model"),
            prompt_version=self._PROMPT_VERSION,
            task_id=task_id,
            policy=dict(task_policy or {}),
        )
