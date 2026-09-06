"""Bounded Agent adjudication for genuinely ambiguous local candidates."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any


VERDICTS = {"accept", "reject", "merge", "split", "pending"}


class NovelAdjudicator:
    """Ask the Agent only for bounded identity/conflict decisions."""

    def __init__(
        self,
        provider=None,
        *,
        repo=None,
        cache=None,
        knowledge_version: str = "v2-local-evidence",
        prompt_version: str = "novel-adjudicate-v1",
        max_candidates: int = 8,
        max_evidence_chars: int = 300,
        local_accept_score: float = 0.85,
    ):
        self._provider = provider
        self._repo = repo
        self._cache = cache
        self.knowledge_version = knowledge_version
        self.prompt_version = prompt_version
        self.max_candidates = max(1, int(max_candidates))
        self.max_evidence_chars = max(40, int(max_evidence_chars))
        self.local_accept_score = max(0.0, min(1.0, float(local_accept_score)))
        self._local_cache: dict[str, list[dict[str, Any]]] = {}

    async def adjudicate(
        self,
        owner_scope: str,
        book_id: int,
        candidates,
    ) -> list[dict[str, Any]]:
        normalized = [self._normalize_candidate(item) for item in candidates or []]
        results: list[dict[str, Any] | None] = [None] * len(normalized)
        ambiguous: list[tuple[int, dict[str, Any]]] = []
        for index, candidate in enumerate(normalized):
            if self._can_accept_locally(candidate):
                results[index] = self._local_decision(candidate)
            else:
                ambiguous.append((index, candidate))

        for start in range(0, len(ambiguous), self.max_candidates):
            batch = ambiguous[start : start + self.max_candidates]
            decisions = await self._adjudicate_batch(owner_scope, int(book_id), [item for _, item in batch])
            by_index = {int(item.get("index")): item for item in decisions if isinstance(item, dict)}
            for relative_index, (original_index, candidate) in enumerate(batch):
                decision = by_index.get(relative_index)
                results[original_index] = self._validated_decision(candidate, decision)
        return [item for item in results if item is not None]

    async def _adjudicate_batch(self, owner_scope: str, book_id: int, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        request_candidates = []
        evidence_ids: set[str] = set()
        for candidate in candidates:
            evidence = []
            for index, item in enumerate(candidate.get("evidence", [])):
                evidence_id = self._evidence_id(item, index)
                evidence_ids.add(evidence_id)
                evidence.append(
                    {
                        "id": evidence_id,
                        "chapter_id": item.get("chapter_id"),
                        "chapter_num": item.get("chapter_num"),
                        "start_offset": item.get("start_offset"),
                        "end_offset": item.get("end_offset"),
                        "text": str(item.get("text") or "")[: self.max_evidence_chars],
                    }
                )
            request_candidates.append(
                {
                    "name": candidate["name"],
                    "entity_type": candidate["entity_type"],
                    "score": candidate["score"],
                    "mentions": candidate["mentions"],
                    "aliases": candidate.get("aliases", []),
                    "subtype": candidate.get("subtype", ""),
                    "evidence": evidence,
                }
            )
        candidate_ids = await self._persist_candidates(owner_scope, book_id, candidates, request_candidates)
        payload = {
            "knowledge_version": self.knowledge_version,
            "prompt_version": self.prompt_version,
            "instructions": "Return strict JSON: {decisions:[{index,verdict,evidence_ids,reason}]}.",
            "candidates": request_candidates,
        }
        cache_key = self._cache_key(owner_scope, book_id, request_candidates)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            await self._update_candidates(owner_scope, candidate_ids, cached)
            return cached
        try:
            response = await self._invoke_provider(owner_scope, payload)
            decisions = self._parse_response(response)
            if any(
                evidence_id not in evidence_ids
                for decision in decisions
                for evidence_id in decision.get("evidence_ids", [])
            ):
                raise ValueError("Agent response cited evidence not present in request")
            await self._cache_set(cache_key, decisions)
            await self._update_candidates(owner_scope, candidate_ids, decisions)
            return decisions
        except Exception as exc:
            decisions = [
                {"index": index, "verdict": "pending", "reason": str(exc)[:240], "evidence_ids": []}
                for index in range(len(candidates))
            ]
            await self._update_candidates(owner_scope, candidate_ids, decisions)
            return decisions

    async def _persist_candidates(
        self,
        owner_scope: str,
        book_id: int,
        candidates: list[dict[str, Any]],
        request_candidates: list[dict[str, Any]],
    ) -> list[int]:
        method = getattr(self._repo, "upsert_adjudication_candidate", None) if self._repo is not None else None
        if not callable(method):
            return []
        from app.domain.entities.novel_runtime import NovelAdjudicationCandidate

        ids: list[int] = []
        for candidate, bounded in zip(candidates, request_candidates):
            raw = json.dumps(candidate, ensure_ascii=False, sort_keys=True, default=str)
            candidate_key = "candidate:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
            evidence = bounded.get("evidence") or []
            chapter_id = evidence[0].get("chapter_id") if evidence else None
            record = NovelAdjudicationCandidate(
                owner_scope=owner_scope,
                book_id=int(book_id),
                chapter_id=int(chapter_id) if chapter_id is not None else None,
                candidate_key=candidate_key,
                content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                candidate_payload={key: value for key, value in candidate.items() if key != "evidence"},
                evidence_payload=evidence,
            )
            try:
                value = method(record)
                value = await value if inspect.isawaitable(value) else value
                ids.append(int(getattr(value, "id", 0) or 0))
            except Exception:
                # The queue is observability/recovery state; it must never
                # turn an otherwise safe bounded adjudication into a failure.
                ids.append(0)
        return ids

    async def _update_candidates(
        self, owner_scope: str, candidate_ids: list[int], decisions: list[dict[str, Any]]
    ) -> None:
        method = getattr(self._repo, "update_adjudication_candidate", None) if self._repo is not None else None
        if not callable(method):
            return
        for candidate_id, decision in zip(candidate_ids, decisions):
            if not candidate_id or not isinstance(decision, dict):
                continue
            try:
                value = method(
                    owner_scope,
                    candidate_id,
                    status=str(decision.get("verdict") or "pending"),
                    decision=decision,
                    attempts=1,
                )
                if inspect.isawaitable(value):
                    await value
            except Exception:
                continue

    async def _invoke_provider(self, owner_scope: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._provider is None:
            raise RuntimeError("novel adjudicator provider is not configured")
        quota_scope = ("user", str(owner_scope).split(":", 1)[-1])
        specialized = getattr(self._provider, "invoke_novel_adjudicate", None)
        if callable(specialized):
            return await specialized(
                owner_scope=owner_scope,
                model=None,
                payload=payload,
                quota_scope=quota_scope,
            )
        method = getattr(self._provider, "invoke_chat", None)
        if not callable(method):
            raise RuntimeError("provider does not support adjudication")
        return await method(
            provider_group="novel_adjudicate",
            model=None,
            payload={
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "只裁决候选，不得创造未提供的证据；仅输出 JSON。"},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
                ],
            },
            quota_scope=quota_scope,
        )

    @staticmethod
    def _parse_response(response: Any) -> list[dict[str, Any]]:
        if isinstance(response, dict):
            output = response.get("output", response)
            if isinstance(output, dict):
                raw = output.get("text") or output.get("content") or output.get("decisions")
            else:
                raw = output
        else:
            raw = response
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            raw = raw.get("decisions", [])
        if not isinstance(raw, list):
            raise ValueError("Agent returned invalid adjudication JSON")
        parsed = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            verdict = str(item.get("verdict") or "pending").strip().lower()
            if verdict not in VERDICTS:
                verdict = "pending"
            evidence_ids = item.get("evidence_ids") or []
            if not isinstance(evidence_ids, list):
                evidence_ids = []
            parsed.append(
                {
                    "index": int(item.get("index", len(parsed))),
                    "verdict": verdict,
                    "evidence_ids": [str(value) for value in evidence_ids],
                    "reason": str(item.get("reason") or "")[:300],
                }
            )
        return parsed

    def _validated_decision(self, candidate: dict[str, Any], decision: dict[str, Any] | None) -> dict[str, Any]:
        if not decision or decision.get("verdict") not in VERDICTS:
            return self._pending(candidate, "Agent did not return a decision")
        allowed = {self._evidence_id(item, index) for index, item in enumerate(candidate.get("evidence", []))}
        cited = [str(item) for item in decision.get("evidence_ids", [])]
        if any(item not in allowed for item in cited):
            return self._pending(candidate, "Agent response cited invalid evidence")
        return {
            "name": candidate["name"],
            "entity_type": candidate["entity_type"],
            "verdict": decision["verdict"],
            "status": "accepted" if decision["verdict"] == "accept" else decision["verdict"],
            "reason": decision.get("reason", ""),
            "evidence_ids": cited,
            "source": "agent",
        }

    def _can_accept_locally(self, candidate: dict[str, Any]) -> bool:
        return (
            candidate["score"] >= self.local_accept_score
            and candidate.get("status") not in {"candidate", "conflict"}
            and bool(candidate.get("evidence"))
        )

    def _local_decision(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": candidate["name"],
            "entity_type": candidate["entity_type"],
            "verdict": "accept",
            "status": "accepted",
            "reason": "local evidence threshold",
            "evidence_ids": [self._evidence_id(item, index) for index, item in enumerate(candidate.get("evidence", []))],
            "source": "local",
        }

    @staticmethod
    def _pending(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "name": candidate["name"],
            "entity_type": candidate["entity_type"],
            "verdict": "pending",
            "status": "pending",
            "reason": reason,
            "evidence_ids": [],
            "source": "agent",
        }

    @staticmethod
    def _normalize_candidate(candidate: Any) -> dict[str, Any]:
        if isinstance(candidate, dict):
            data = dict(candidate)
        elif is_dataclass(candidate):
            data = asdict(candidate)
        else:
            data = dict(vars(candidate))
        return {
            "name": str(data.get("name") or "").strip(),
            "entity_type": str(getattr(data.get("entity_type"), "value", data.get("entity_type") or "entity")),
            "score": max(0.0, min(1.0, float(data.get("score", data.get("confidence", 0.0)) or 0.0))),
            "mentions": int(data.get("mentions", data.get("mention_count", 0)) or 0),
            "aliases": [str(item) for item in data.get("aliases", []) or []],
            "subtype": str(data.get("subtype") or ""),
            "status": str(data.get("status") or "candidate"),
            "evidence": [NovelAdjudicator._normalize_evidence(item) for item in data.get("evidence", []) or []],
        }

    @staticmethod
    def _normalize_evidence(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return dict(item)
        if is_dataclass(item):
            return asdict(item)
        if hasattr(item, "__dict__"):
            return dict(vars(item))
        return {"text": str(item)}

    @staticmethod
    def _evidence_id(item: dict[str, Any], index: int) -> str:
        raw = "|".join(
            str(item.get(key, ""))
            for key in ("chapter_id", "chapter_num", "start_offset", "end_offset", "text")
        )
        return f"evidence:{index}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"

    def _cache_key(self, owner_scope: str, book_id: int, candidates: list[dict[str, Any]]) -> str:
        raw = json.dumps(
            [owner_scope, int(book_id), self.knowledge_version, self.prompt_version, candidates],
            ensure_ascii=False,
            sort_keys=True,
        )
        return "novel:adjudicate:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _cache_get(self, key: str):
        if key in self._local_cache:
            return self._local_cache[key]
        getter = getattr(self._cache, "get", None) if self._cache is not None else None
        if not callable(getter):
            return None
        value = getter(key)
        return await value if inspect.isawaitable(value) else value

    async def _cache_set(self, key: str, value) -> None:
        self._local_cache[key] = value
        setter = getattr(self._cache, "set", None) if self._cache is not None else None
        if not callable(setter):
            return
        try:
            result = setter(key, value, ttl=3600)
        except TypeError:
            result = setter(key, value, expire=3600)
        if inspect.isawaitable(result):
            await result
