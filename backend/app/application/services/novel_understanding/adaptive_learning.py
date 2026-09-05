"""Conservative, book-scoped learning for deterministic novel extraction."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.domain.entities.novel import EvolutionFeedback, EvolutionRule


RULE_TYPES = {
    "alias": "novel_alias",
    "negative": "novel_negative_term",
    "weight": "novel_feature_weight",
}
WEIGHT_MIN = 0.5
WEIGHT_MAX = 1.5


class AdaptiveLearningService:
    """Turn only structured, evidence-backed feedback into local profile rules."""

    def __init__(self, *, repo, min_support: int = 2):
        self._repo = repo
        self.min_support = max(1, int(min_support))

    async def record_signal(
        self,
        owner_scope: str,
        book_id: int,
        *,
        kind: str,
        name: str = "",
        canonical_name: str = "",
        feature: str = "",
        delta: float = 0.0,
        evidence_ids: list[str] | tuple[str, ...] = (),
        content_hash: str = "",
        source: str = "adjudication",
        explicit: bool = False,
        reason: str = "",
    ) -> EvolutionRule | None:
        if source not in {"adjudication", "user_correction"}:
            return None
        if kind not in RULE_TYPES:
            raise ValueError(f"unsupported learning signal: {kind}")
        pattern = str(feature or name).strip()
        replacement = str(canonical_name or "").strip() if kind == "alias" else ""
        if not pattern or (kind == "alias" and not replacement):
            raise ValueError("learning signal is incomplete")

        rule_type = RULE_TYPES[kind]
        existing_rules = await self._repo_call(
            "list_evolution_rules",
            owner_scope,
            int(book_id),
            rule_type=rule_type,
            active=None,
            limit=100,
        )
        existing = next((item for item in existing_rules or [] if item.pattern == pattern), None)
        condition = self._condition(existing)
        fingerprints = set(str(item) for item in condition.get("content_hashes", []) if item)
        fingerprint = str(content_hash or "").strip()
        if not fingerprint:
            fingerprint = hashlib.sha256(
                json.dumps(sorted(str(item) for item in evidence_ids), ensure_ascii=False).encode("utf-8")
            ).hexdigest()
        if fingerprint in fingerprints and not explicit:
            return existing
        fingerprints.add(fingerprint)
        support = max(int(condition.get("support_count", 0) or 0), int(existing.success_count if existing else 0))
        support += 1
        if explicit:
            support = max(support, self.min_support)

        if kind == "weight":
            previous = float(condition.get("multiplier", 1.0) or 1.0)
            multiplier = max(WEIGHT_MIN, min(WEIGHT_MAX, previous + float(delta)))
            replacement = str(multiplier)
        else:
            multiplier = None

        condition = {
            **condition,
            "support_count": support,
            "threshold": self.min_support,
            "content_hashes": sorted(fingerprints)[-32:],
            "evidence_ids": sorted({str(item) for item in [*condition.get("evidence_ids", []), *evidence_ids] if item})[-64:],
            "source": source,
        }
        if multiplier is not None:
            condition["multiplier"] = multiplier
        feedback = EvolutionFeedback(
            book_id=int(book_id),
            feedback_type="user_correction" if source == "user_correction" else "structured_adjudication",
            target_type="novel_extraction",
            target_id=0,
            original_value=pattern,
            corrected_value=replacement,
            reason=json.dumps(
                {"reason": reason, "evidence_ids": list(evidence_ids), "content_hash": fingerprint},
                ensure_ascii=False,
                sort_keys=True,
            ),
            confidence=1.0 if explicit else min(1.0, support / max(1, self.min_support)),
        )
        rule = EvolutionRule(
            book_id=int(book_id),
            rule_type=rule_type,
            pattern=pattern,
            replacement=replacement,
            condition=json.dumps(condition, ensure_ascii=False, sort_keys=True),
            hit_count=support,
            success_count=support,
            failure_count=0,
            active=explicit or support >= self.min_support,
        )
        return await self._repo_call("apply_evolution_update", owner_scope, int(book_id), feedback, rule)

    async def get_profile(self, owner_scope: str, book_id: int) -> dict[str, Any]:
        rules = await self._repo_call(
            "list_evolution_rules",
            owner_scope,
            int(book_id),
            active=True,
            limit=1000,
        )
        aliases: dict[str, str] = {}
        negative_terms: list[str] = []
        feature_weights: dict[str, float] = {}
        for rule in rules or []:
            if rule.rule_type == RULE_TYPES["alias"]:
                aliases[rule.pattern] = rule.replacement
            elif rule.rule_type == RULE_TYPES["negative"]:
                negative_terms.append(rule.pattern)
            elif rule.rule_type == RULE_TYPES["weight"]:
                condition = self._condition(rule)
                try:
                    feature_weights[rule.pattern] = max(
                        WEIGHT_MIN,
                        min(WEIGHT_MAX, float(condition.get("multiplier", rule.replacement) or 1.0)),
                    )
                except (TypeError, ValueError):
                    continue
        profile = {
            "aliases": dict(sorted(aliases.items())),
            "negative_terms": sorted(set(negative_terms)),
            "feature_weights": dict(sorted(feature_weights.items())),
        }
        raw = json.dumps(profile, ensure_ascii=False, sort_keys=True)
        profile["profile_version"] = "learning-v1:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return profile

    async def learn_from_adjudication(
        self, owner_scope: str, book_id: int, candidate: dict[str, Any], decision: dict[str, Any]
    ) -> EvolutionRule | None:
        verdict = str(decision.get("verdict") or "pending")
        if verdict in {"accept", "merge"} and candidate.get("aliases"):
            alias = str(candidate.get("aliases")[0] or "").strip()
            canonical_name = str(candidate.get("name") or "").strip()
            if not alias or not canonical_name or alias == canonical_name:
                return None
            return await self.record_signal(
                owner_scope,
                book_id,
                kind="alias",
                name=alias,
                canonical_name=canonical_name,
                evidence_ids=decision.get("evidence_ids") or [],
                content_hash=str(candidate.get("content_hash") or ""),
            )
        if verdict == "reject":
            return await self.record_signal(
                owner_scope,
                book_id,
                kind="negative",
                name=str(candidate.get("name") or ""),
                evidence_ids=decision.get("evidence_ids") or [],
                content_hash=str(candidate.get("content_hash") or ""),
            )
        return None

    async def _repo_call(self, name: str, owner_scope: str, *args, **kwargs):
        method = getattr(self._repo, name, None)
        if not callable(method):
            raise RuntimeError(f"learning repository method is unavailable: {name}")
        value = method(owner_scope, *args, **kwargs)
        if hasattr(value, "__await__"):
            value = await value
        return value

    @staticmethod
    def _condition(rule) -> dict[str, Any]:
        if rule is None:
            return {}
        value = getattr(rule, "condition", {})
        if isinstance(value, dict):
            return dict(value)
        try:
            parsed = json.loads(value or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
