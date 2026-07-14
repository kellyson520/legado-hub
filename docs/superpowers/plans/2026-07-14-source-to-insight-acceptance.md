# Source to Insight Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic source-to-insight acceptance runner that proves the existing distributed source, reading, complement, knowledge, and optional AI analysis services work together without turning the whole flow over to an autonomous agent.

**Architecture:** Add a narrow application service that orchestrates existing services in a fixed order and emits a JSON report. The service uses fakes in tests, existing source/reading/complement/knowledge services in runtime, and invokes the provider platform only for the optional compact evidence analysis node. A small smoke script and optional frontend report page make the acceptance path runnable by operators.

**Tech Stack:** Python 3, FastAPI service patterns, Pydantic-style dict payloads, pytest, existing provider platform, React 18, TypeScript, Vitest.

---

## File Structure

- Create `backend/app/application/services/source_to_insight_acceptance_service.py`: deterministic acceptance orchestration, report shaping, optional AI analysis normalization.
- Create `backend/scripts/smoke_source_to_insight.py`: CLI entry point for fixture-mode, real-source-mode, optional AI, and JSON report output.
- Create `backend/tests/fixtures/source_to_insight_sources.json`: tiny source fixture used by script contract tests; do not use the large local `测试源/shareBookSource.json` in tests.
- Create `backend/tests/test_source_to_insight_acceptance_service.py`: unit tests with fakes for deterministic flow and optional AI flow.
- Create `backend/tests/test_smoke_source_to_insight.py`: CLI/script contract tests.
- Modify `backend/app/infrastructure/persistence/factory.py`: add `build_source_to_insight_acceptance_service()` composition helper.
- Optionally create `frontend/src/api/modules/sourceInsight.ts`: typed client for a report endpoint only if Task 4 is implemented.
- Optionally create `frontend/src/features/novel/SourceInsightWorkbenchPage.tsx`: minimal operator report UI only after backend runner is stable.
- Optionally modify `frontend/src/app/router.tsx` and `frontend/src/app/navigation.tsx`: add `/novel/source-insight`.

Do not stage or commit:

- CRLF-only drift currently present in backend tests/docs.
- `测试源/shareBookSource.json` path movement or the deleted garbled-path source fixture.
- Unrelated checkpoint PID/report updates.

## Task 1: Acceptance Service Deterministic Pipeline

**Files:**
- Create: `backend/app/application/services/source_to_insight_acceptance_service.py`
- Test: `backend/tests/test_source_to_insight_acceptance_service.py`

- [ ] **Step 1: Write the failing deterministic service test**

Create `backend/tests/test_source_to_insight_acceptance_service.py` with fakes that exercise search, toc, content, complement, character calibration, and knowledge proposal creation without AI:

```python
import pytest


class FakeSourceRuntime:
    async def import_legado_sources(self, payload, actor_id):
        return {
            "items": [
                {"index": 0, "status": "created", "source_url": "https://a.example.com", "source_version_id": "sv-a"},
                {"index": 1, "status": "skipped_duplicate", "source_url": "https://b.example.com"},
            ]
        }

    async def validate_rule_version(self, source_version_id, actor_id):
        return {
            "source_version_id": source_version_id,
            "score": 85,
            "grade": "B",
            "step_results": {"search": {"passed": True}, "toc": {"passed": True}, "content": {"passed": True}},
            "diagnostics": [],
            "publish_allowed": True,
        }


class FakeReading:
    async def search_books(self, keyword, source_ids=None, limit_per_source=3, author_hint=None, routing_mode="auto", include_health=True):
        return {
            "keyword": keyword,
            "items": [
                {
                    "source_id": 7,
                    "name": keyword,
                    "author": author_hint or "唐家三少",
                    "bookUrl": "https://a.example.com/book/1",
                    "sourceName": "源A",
                    "sourceUrl": "https://a.example.com",
                    "health_status": "healthy",
                    "route_decision": "allow",
                },
                {
                    "source_id": 33,
                    "name": keyword,
                    "author": author_hint or "唐家三少",
                    "bookUrl": "https://b.example.com/book/1",
                    "sourceName": "源B",
                    "sourceUrl": "https://b.example.com",
                    "health_status": "healthy",
                    "route_decision": "allow",
                },
            ],
            "route_summary": {"selected_source_ids": [7, 33], "routing_mode": routing_mode, "include_health": include_health},
        }

    async def get_book_toc(self, source_id, book_url, book_name=None, author_hint=None, routing_mode="auto"):
        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "book_url": book_url,
            "fallback_used": False,
            "chapters": [
                {"title": "第一章 觉醒", "url": f"{book_url}/1", "index": 0},
                {"title": "第二章 入学", "url": f"{book_url}/2", "index": 1},
            ],
        }

    async def get_chapter_content(self, source_id, chapter_url, book_name=None, author_hint=None, chapter_title=None, chapter_index=None, routing_mode="auto"):
        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "chapter_url": chapter_url,
            "fallback_used": False,
            "title": chapter_title or "第一章 觉醒",
            "content": f"唐三在源{source_id}的章节里觉醒武魂，并决定继续修炼。",
            "nextUrl": "",
        }


class FakeComplement:
    async def complement_chapter_candidates(self, book_name, chapter_title, chapter_num, items, reference_content="", merge_strategy="hybrid"):
        return {
            "book_name": book_name,
            "chapter_title": chapter_title,
            "chapter_num": chapter_num,
            "status": "success",
            "successful_sources": len(items),
            "failed_sources": 0,
            "final_content": "唐三觉醒武魂，理解魂师规则，并决定修炼。",
            "merged_from": [item["source_url"] for item in items],
            "source_results": [
                {"source_name": item["source_name"], "source_url": item["source_url"], "success": True, "word_count": 28, "error": None}
                for item in items
            ],
        }

    async def aclose(self):
        return None


class FakeCharacterCalibration:
    async def calibrate(self, keyword, items, actor_id="system"):
        return {
            "keyword": keyword,
            "items": [{**items[0], "characters": ["唐三", "武魂"]}],
            "pairwise": [],
            "used_provider": False,
            "provider_result": None,
        }


class FakeKnowledge:
    def propose_relation(self, **kwargs):
        return type("Proposal", (), {"id": "rel-1", "proposal_type": "character_relation", "status": "candidate", "payload": {"relation": kwargs["relation"]}})()

    def propose_plot_event(self, **kwargs):
        return type("Proposal", (), {"id": "plot-1", "proposal_type": "plot_event", "status": "candidate", "payload": {"event_title": kwargs["event_title"]}})()

    def propose_world_rule(self, **kwargs):
        return type("Proposal", (), {"id": "world-1", "proposal_type": "world_rule", "status": "candidate", "payload": {"rule_name": kwargs["rule_name"]}})()


@pytest.mark.asyncio
async def test_acceptance_service_runs_distributed_pipeline_without_ai():
    from app.application.services.source_to_insight_acceptance_service import (
        SourceToInsightAcceptanceService,
        SourceToInsightScenario,
    )

    service = SourceToInsightAcceptanceService(
        source_runtime=FakeSourceRuntime(),
        reading=FakeReading(),
        complement=FakeComplement(),
        character_calibration=FakeCharacterCalibration(),
        knowledge=FakeKnowledge(),
        provider_platform=None,
    )

    report = await service.run(SourceToInsightScenario(
        book_name="斗罗大陆",
        author_hint="唐家三少",
        chapter_index=0,
        chapter_title="第一章",
        source_records=[{"bookSourceName": "源A", "bookSourceUrl": "https://a.example.com"}],
        source_limit=2,
        use_ai=False,
        actor_id="1",
    ))

    assert report["status"] == "passed"
    assert [step["name"] for step in report["steps"]] == [
        "source_import",
        "source_validation",
        "search",
        "toc",
        "content",
        "complement",
        "deterministic_insights",
        "knowledge_proposals",
        "ai_analysis",
    ]
    assert report["ai"]["status"] == "skipped"
    assert report["book_candidates"][0]["name"] == "斗罗大陆"
    assert report["complement"]["successful_sources"] == 2
    assert report["insights"]["characters"]
    assert {item["proposal_type"] for item in report["knowledge_proposals"]} == {
        "character_relation",
        "plot_event",
        "world_rule",
    }
```

- [ ] **Step 2: Run the RED deterministic service test**

Run from `backend/`:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py::test_acceptance_service_runs_distributed_pipeline_without_ai -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.application.services.source_to_insight_acceptance_service'`.

- [ ] **Step 3: Implement the service skeleton and deterministic report**

Create `backend/app/application/services/source_to_insight_acceptance_service.py`:

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceToInsightScenario:
    book_name: str
    author_hint: str = ""
    chapter_index: int = 0
    chapter_title: str = ""
    source_records: list[dict[str, Any]] = field(default_factory=list)
    source_json_path: str = ""
    source_limit: int = 5
    use_ai: bool = False
    actor_id: str = "system"
    routing_mode: str = "auto"


class SourceToInsightAcceptanceService:
    def __init__(
        self,
        *,
        source_runtime,
        reading,
        complement,
        character_calibration,
        knowledge,
        provider_platform=None,
        model: str = "gpt-4.1-mini",
    ):
        self._source_runtime = source_runtime
        self._reading = reading
        self._complement = complement
        self._character_calibration = character_calibration
        self._knowledge = knowledge
        self._provider_platform = provider_platform
        self._model = model

    async def run(self, scenario: SourceToInsightScenario) -> dict[str, Any]:
        report = {
            "scenario": self._serialize_scenario(scenario),
            "status": "passed",
            "steps": [],
            "sources": [],
            "book_candidates": [],
            "toc_candidates": [],
            "chapter_candidates": [],
            "complement": {},
            "insights": {
                "characters": [],
                "relations": [],
                "plot_events": [],
                "world_rules": [],
                "timeline": [],
            },
            "knowledge_proposals": [],
            "ai": {
                "used": scenario.use_ai,
                "status": "skipped" if not scenario.use_ai else "not_configured",
                "provider": "",
                "model": "",
                "usage": {},
            },
        }

        import_result = await self._run_step(report, "source_import", self._import_sources, scenario)
        validation_result = await self._run_step(report, "source_validation", self._validate_sources, import_result, scenario)
        report["sources"] = validation_result

        search_result = await self._run_step(report, "search", self._search, scenario)
        report["book_candidates"] = search_result["items"][: scenario.source_limit]

        toc_result = await self._run_step(report, "toc", self._load_toc, report["book_candidates"], scenario)
        report["toc_candidates"] = toc_result

        content_result = await self._run_step(report, "content", self._load_content, toc_result, scenario)
        report["chapter_candidates"] = content_result

        complement_result = await self._run_step(report, "complement", self._run_complement, content_result, scenario)
        report["complement"] = complement_result

        insights = await self._run_step(report, "deterministic_insights", self._deterministic_insights, complement_result, content_result, scenario)
        report["insights"] = insights

        proposals = await self._run_step(report, "knowledge_proposals", self._create_knowledge_proposals, insights, scenario)
        report["knowledge_proposals"] = proposals

        ai_result = await self._run_step(report, "ai_analysis", self._optional_ai_analysis, insights, complement_result, scenario)
        report["ai"] = ai_result
        report["status"] = self._status_from_steps(report["steps"])
        return report

    async def _run_step(self, report: dict[str, Any], name: str, fn, *args):
        started = time.perf_counter()
        try:
            result = await fn(*args)
            status = "passed"
            errors: list[str] = []
        except Exception as exc:
            result = None
            status = "failed"
            errors = [str(exc)]
        report["steps"].append({
            "name": name,
            "status": status,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "summary": self._summary(result),
            "errors": errors,
        })
        if status == "failed":
            return self._empty_step_result(name)
        return result

    async def _import_sources(self, scenario: SourceToInsightScenario) -> dict[str, Any]:
        if not scenario.source_records:
            return {"items": []}
        records = scenario.source_records[: scenario.source_limit]
        return await self._source_runtime.import_legado_sources(records, scenario.actor_id)

    async def _validate_sources(self, import_result: dict[str, Any], scenario: SourceToInsightScenario) -> list[dict[str, Any]]:
        rows = []
        for item in import_result.get("items", []):
            row = dict(item)
            source_version_id = item.get("source_version_id")
            if source_version_id:
                row["validation"] = await self._source_runtime.validate_rule_version(source_version_id, scenario.actor_id)
            rows.append(row)
        return rows

    async def _search(self, scenario: SourceToInsightScenario) -> dict[str, Any]:
        return await self._reading.search_books(
            keyword=scenario.book_name,
            source_ids=None,
            limit_per_source=1,
            author_hint=scenario.author_hint or None,
            routing_mode=scenario.routing_mode,
            include_health=True,
        )

    async def _load_toc(self, book_candidates: list[dict[str, Any]], scenario: SourceToInsightScenario) -> list[dict[str, Any]]:
        rows = []
        for book in book_candidates[: scenario.source_limit]:
            toc = await self._reading.get_book_toc(
                source_id=int(book["source_id"]),
                book_url=book["bookUrl"],
                book_name=scenario.book_name,
                author_hint=scenario.author_hint or None,
                routing_mode=scenario.routing_mode,
            )
            chapter = self._select_chapter(toc.get("chapters", []), scenario)
            rows.append({"book": book, "toc": toc, "selected_chapter": chapter})
        return rows

    async def _load_content(self, toc_candidates: list[dict[str, Any]], scenario: SourceToInsightScenario) -> list[dict[str, Any]]:
        rows = []
        for item in toc_candidates:
            chapter = item.get("selected_chapter") or {}
            book = item["book"]
            if not chapter.get("url"):
                continue
            content = await self._reading.get_chapter_content(
                source_id=int(book["source_id"]),
                chapter_url=chapter["url"],
                book_name=scenario.book_name,
                author_hint=scenario.author_hint or None,
                chapter_title=chapter.get("title") or scenario.chapter_title or None,
                chapter_index=scenario.chapter_index,
                routing_mode=scenario.routing_mode,
            )
            rows.append({"book": book, "chapter": chapter, "content": content})
        return rows

    async def _run_complement(self, chapter_candidates: list[dict[str, Any]], scenario: SourceToInsightScenario) -> dict[str, Any]:
        items = [
            {
                "source_id": int(item["book"]["source_id"]),
                "chapter_url": item["chapter"]["url"],
                "source_name": item["book"].get("sourceName", ""),
                "source_url": item["book"].get("sourceUrl", ""),
            }
            for item in chapter_candidates
        ]
        if not items:
            return {"status": "empty", "successful_sources": 0, "failed_sources": 0, "final_content": "", "source_results": []}
        result = await self._complement.complement_chapter_candidates(
            book_name=scenario.book_name,
            chapter_title=scenario.chapter_title or chapter_candidates[0]["chapter"].get("title", ""),
            chapter_num=scenario.chapter_index + 1,
            items=items,
            reference_content=chapter_candidates[0]["content"].get("content", ""),
        )
        close = getattr(self._complement, "aclose", None)
        if close is not None:
            await close()
        return result

    async def _deterministic_insights(self, complement_result: dict[str, Any], chapter_candidates: list[dict[str, Any]], scenario: SourceToInsightScenario) -> dict[str, Any]:
        excerpts = [
            {
                "source_id": item["book"]["source_id"],
                "name": item["book"].get("name", scenario.book_name),
                "author": item["book"].get("author", scenario.author_hint),
                "excerpt": self._excerpt(item["content"].get("content", "")),
            }
            for item in chapter_candidates
        ]
        calibration = await self._character_calibration.calibrate(
            keyword=scenario.book_name,
            items=excerpts,
            actor_id=scenario.actor_id,
        )
        evidence = self._excerpt(complement_result.get("final_content", ""))
        characters = calibration.get("items", [{}])[0].get("characters", []) if calibration.get("items") else []
        relation = {
            "subject": characters[0] if characters else scenario.book_name,
            "relation": "appears_in",
            "object_name": scenario.chapter_title or "selected_chapter",
            "evidence": evidence,
        }
        plot_event = {
            "event_title": scenario.chapter_title or "Selected chapter event",
            "summary": evidence,
            "evidence": evidence,
        }
        world_rule = {
            "rule_name": f"{scenario.book_name} setting signal",
            "description": evidence,
            "evidence": evidence,
        }
        return {
            "characters": characters,
            "relations": [relation],
            "plot_events": [plot_event],
            "world_rules": [world_rule],
            "timeline": [{"chapter_index": scenario.chapter_index, "title": scenario.chapter_title, "summary": evidence}],
        }

    async def _create_knowledge_proposals(self, insights: dict[str, Any], scenario: SourceToInsightScenario) -> list[dict[str, Any]]:
        work_id = self._stable_work_id(scenario.book_name, scenario.author_hint)
        source_chapter_id = f"{work_id}:chapter:{scenario.chapter_index}"
        proposals = []
        for item in insights.get("relations", [])[:1]:
            proposal = self._knowledge.propose_relation(
                work_id=work_id,
                source_chapter_id=source_chapter_id,
                evidence=item.get("evidence", ""),
                relation=item.get("relation", "appears_in"),
                actor_id=scenario.actor_id,
            )
            proposals.append(self._serialize_proposal(proposal))
        for item in insights.get("plot_events", [])[:1]:
            proposal = self._knowledge.propose_plot_event(
                work_id=work_id,
                source_chapter_id=source_chapter_id,
                evidence=item.get("evidence", ""),
                event_title=item.get("event_title", "Selected chapter event"),
                summary=item.get("summary", ""),
                actor_id=scenario.actor_id,
            )
            proposals.append(self._serialize_proposal(proposal))
        for item in insights.get("world_rules", [])[:1]:
            proposal = self._knowledge.propose_world_rule(
                work_id=work_id,
                source_chapter_id=source_chapter_id,
                evidence=item.get("evidence", ""),
                rule_name=item.get("rule_name", "World rule"),
                description=item.get("description", ""),
                actor_id=scenario.actor_id,
            )
            proposals.append(self._serialize_proposal(proposal))
        return proposals

    async def _optional_ai_analysis(self, insights: dict[str, Any], complement_result: dict[str, Any], scenario: SourceToInsightScenario) -> dict[str, Any]:
        if not scenario.use_ai:
            return {"used": False, "status": "skipped", "provider": "", "model": "", "usage": {}}
        if self._provider_platform is None:
            return {"used": True, "status": "not_configured", "provider": "", "model": self._model, "usage": {}}
        payload = {
            "task": "source_to_insight_analysis",
            "book_name": scenario.book_name,
            "author_hint": scenario.author_hint,
            "evidence": self._excerpt(complement_result.get("final_content", ""), limit=2000),
            "deterministic_insights": insights,
            "messages": [
                {"role": "system", "content": "Return compact JSON analysis for characters, plot, world rules, and timeline."},
                {"role": "user", "content": self._analysis_prompt(scenario, complement_result, insights)},
            ],
        }
        invocation = await self._provider_platform.invoke_chat(
            provider_group="novel",
            model=self._model,
            payload=payload,
            quota_scope=("user", scenario.actor_id),
        )
        return {
            "used": True,
            "status": "succeeded",
            "provider": invocation.get("provider_name", ""),
            "model": invocation.get("model", self._model),
            "usage": invocation.get("usage", {}),
            "output": invocation.get("output", {}),
        }

    @staticmethod
    def _select_chapter(chapters: list[dict[str, Any]], scenario: SourceToInsightScenario) -> dict[str, Any]:
        if not chapters:
            return {}
        for chapter in chapters:
            if int(chapter.get("index", -1)) == scenario.chapter_index:
                return chapter
        if scenario.chapter_title:
            for chapter in chapters:
                if scenario.chapter_title in str(chapter.get("title", "")):
                    return chapter
        return chapters[0]

    @staticmethod
    def _excerpt(value: str, limit: int = 500) -> str:
        text = " ".join((value or "").split())
        return text[:limit]

    @staticmethod
    def _stable_work_id(book_name: str, author_hint: str) -> str:
        raw = f"{book_name}:{author_hint}".strip(":")
        return raw.replace("/", "_").replace(" ", "_") or "unknown_work"

    @staticmethod
    def _serialize_proposal(proposal) -> dict[str, Any]:
        return {
            "id": proposal.id,
            "proposal_type": proposal.proposal_type,
            "status": proposal.status,
            "payload": getattr(proposal, "payload", {}),
        }

    @staticmethod
    def _serialize_scenario(scenario: SourceToInsightScenario) -> dict[str, Any]:
        return {
            "book_name": scenario.book_name,
            "author_hint": scenario.author_hint,
            "chapter_index": scenario.chapter_index,
            "chapter_title": scenario.chapter_title,
            "source_limit": scenario.source_limit,
            "use_ai": scenario.use_ai,
            "routing_mode": scenario.routing_mode,
        }

    @staticmethod
    def _analysis_prompt(scenario: SourceToInsightScenario, complement_result: dict[str, Any], insights: dict[str, Any]) -> str:
        return (
            f"Book: {scenario.book_name}\n"
            f"Author: {scenario.author_hint}\n"
            f"Chapter: {scenario.chapter_title or scenario.chapter_index}\n"
            f"Evidence: {SourceToInsightAcceptanceService._excerpt(complement_result.get('final_content', ''), 2000)}\n"
            f"Deterministic candidates: {insights}\n"
            "Return JSON with characters, relations, plot_events, world_rules, timeline, confidence, notes."
        )

    @staticmethod
    def _summary(result) -> dict[str, Any]:
        if result is None:
            return {}
        if isinstance(result, list):
            return {"count": len(result)}
        if isinstance(result, dict):
            keys = [key for key in ("status", "successful_sources", "failed_sources", "score", "grade") if key in result]
            return {key: result[key] for key in keys} or {"keys": sorted(result.keys())[:8]}
        return {"type": type(result).__name__}

    @staticmethod
    def _empty_step_result(name: str):
        if name in {"source_validation", "toc", "content", "knowledge_proposals"}:
            return []
        if name == "search":
            return {"items": [], "route_summary": {}}
        if name == "deterministic_insights":
            return {"characters": [], "relations": [], "plot_events": [], "world_rules": [], "timeline": []}
        if name == "ai_analysis":
            return {"used": False, "status": "failed", "provider": "", "model": "", "usage": {}}
        return {}

    @staticmethod
    def _status_from_steps(steps: list[dict[str, Any]]) -> str:
        failed = [step for step in steps if step["status"] == "failed"]
        if not failed:
            return "passed"
        critical = {"search", "toc", "content", "complement"}
        if any(step["name"] in critical for step in failed):
            return "failed"
        return "partial"
```

- [ ] **Step 4: Run the deterministic service test**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py::test_acceptance_service_runs_distributed_pipeline_without_ai -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/application/services/source_to_insight_acceptance_service.py backend/tests/test_source_to_insight_acceptance_service.py
git commit -m "feat: add source insight acceptance service"
```

## Task 2: Optional AI Analysis Node Contract

**Files:**
- Modify: `backend/app/application/services/source_to_insight_acceptance_service.py`
- Test: `backend/tests/test_source_to_insight_acceptance_service.py`

- [ ] **Step 1: Add the failing optional AI test**

Append to `backend/tests/test_source_to_insight_acceptance_service.py`:

```python
class FakeProviderPlatform:
    async def invoke_chat(self, provider_group, model, payload, quota_scope):
        assert provider_group == "novel"
        assert model == "gpt-4.1-mini"
        assert quota_scope == ("user", "1")
        assert payload["task"] == "source_to_insight_analysis"
        assert len(payload["evidence"]) <= 2000
        assert "messages" in payload
        return {
            "provider_name": "fake-openai",
            "model": model,
            "output": {
                "text": '{"characters":["唐三"],"world_rules":[{"rule_name":"武魂觉醒"}],"timeline":[{"chapter_index":0}]}',
                "raw": {"id": "chatcmpl-test"},
            },
            "usage": {"input_tokens": 120, "output_tokens": 40, "total_tokens": 160},
        }


@pytest.mark.asyncio
async def test_acceptance_service_uses_ai_only_for_compact_analysis_node():
    from app.application.services.source_to_insight_acceptance_service import (
        SourceToInsightAcceptanceService,
        SourceToInsightScenario,
    )

    service = SourceToInsightAcceptanceService(
        source_runtime=FakeSourceRuntime(),
        reading=FakeReading(),
        complement=FakeComplement(),
        character_calibration=FakeCharacterCalibration(),
        knowledge=FakeKnowledge(),
        provider_platform=FakeProviderPlatform(),
    )

    report = await service.run(SourceToInsightScenario(
        book_name="斗罗大陆",
        author_hint="唐家三少",
        chapter_index=0,
        chapter_title="第一章",
        source_records=[{"bookSourceName": "源A", "bookSourceUrl": "https://a.example.com"}],
        source_limit=2,
        use_ai=True,
        actor_id="1",
    ))

    assert report["status"] == "passed"
    assert report["ai"]["used"] is True
    assert report["ai"]["status"] == "succeeded"
    assert report["ai"]["provider"] == "fake-openai"
    assert report["ai"]["usage"]["total_tokens"] == 160
    assert report["steps"][-1]["name"] == "ai_analysis"
```

- [ ] **Step 2: Run the optional AI test**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py::test_acceptance_service_uses_ai_only_for_compact_analysis_node -q
```

Expected: PASS if Task 1 implementation already includes `_optional_ai_analysis()`. If it fails, adjust only `_optional_ai_analysis()` so it calls the provider platform once and records sanitized `output` and `usage`.

- [ ] **Step 3: Add an AI failure fallback test**

Append:

```python
class FailingProviderPlatform:
    async def invoke_chat(self, provider_group, model, payload, quota_scope):
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
async def test_acceptance_service_marks_ai_failed_without_losing_deterministic_results():
    from app.application.services.source_to_insight_acceptance_service import (
        SourceToInsightAcceptanceService,
        SourceToInsightScenario,
    )

    service = SourceToInsightAcceptanceService(
        source_runtime=FakeSourceRuntime(),
        reading=FakeReading(),
        complement=FakeComplement(),
        character_calibration=FakeCharacterCalibration(),
        knowledge=FakeKnowledge(),
        provider_platform=FailingProviderPlatform(),
    )

    report = await service.run(SourceToInsightScenario(
        book_name="斗罗大陆",
        chapter_index=0,
        source_records=[{"bookSourceName": "源A", "bookSourceUrl": "https://a.example.com"}],
        use_ai=True,
        actor_id="1",
    ))

    assert report["status"] == "partial"
    assert report["ai"]["status"] == "failed"
    assert report["insights"]["characters"]
    assert report["knowledge_proposals"]
```

- [ ] **Step 4: Implement failed AI result preservation**

Modify `_run_step()` or `_optional_ai_analysis()` so provider exceptions do not erase deterministic insights. The simplest implementation is to catch provider errors inside `_optional_ai_analysis()`:

```python
        try:
            invocation = await self._provider_platform.invoke_chat(...)
        except Exception as exc:
            return {
                "used": True,
                "status": "failed",
                "provider": "",
                "model": self._model,
                "usage": {},
                "error": str(exc),
            }
```

Then change `_status_from_steps()` to treat an AI step returning `{"status": "failed"}` as `partial`. If using this approach, `_run_step()` still records the step as `passed`; the `ai.status` field is the semantic failure marker.

- [ ] **Step 5: Run optional AI tests**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/app/application/services/source_to_insight_acceptance_service.py backend/tests/test_source_to_insight_acceptance_service.py
git commit -m "test: cover optional AI analysis in source insight acceptance"
```

## Task 3: Smoke Script and Tiny Fixture

**Files:**
- Create: `backend/scripts/smoke_source_to_insight.py`
- Create: `backend/tests/fixtures/source_to_insight_sources.json`
- Create: `backend/tests/test_smoke_source_to_insight.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`

- [ ] **Step 1: Add the tiny fixture**

Create `backend/tests/fixtures/source_to_insight_sources.json`:

```json
[
  {
    "bookSourceName": "Fixture Source A",
    "bookSourceUrl": "https://a.example.com",
    "enabled": true,
    "searchUrl": "https://a.example.com/search?key={{key}}",
    "ruleSearch": {
      "bookList": ".book",
      "name": ".title",
      "author": ".author",
      "bookUrl": "a@href"
    },
    "ruleToc": {
      "chapterList": "#list a",
      "chapterName": "text",
      "chapterUrl": "href"
    },
    "ruleContent": {
      "content": "#content"
    }
  }
]
```

- [ ] **Step 2: Write the failing script contract test**

Create `backend/tests/test_smoke_source_to_insight.py`:

```python
import json
import subprocess
import sys
from pathlib import Path


def test_smoke_script_fixture_mode_writes_report(tmp_path):
    report_path = tmp_path / "source-to-insight-report.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "smoke_source_to_insight.py"
    fixture = Path(__file__).resolve().parent / "fixtures" / "source_to_insight_sources.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--fixture-mode",
            "--source-json",
            str(fixture),
            "--book-name",
            "斗罗大陆",
            "--author-hint",
            "唐家三少",
            "--chapter-index",
            "0",
            "--output",
            str(report_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["scenario"]["book_name"] == "斗罗大陆"
    assert report["status"] in {"passed", "partial"}
    assert report["ai"]["status"] == "skipped"
    assert [step["name"] for step in report["steps"]]
```

- [ ] **Step 3: Run the RED script contract test**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_smoke_source_to_insight.py -q
```

Expected: FAIL because `backend/scripts/smoke_source_to_insight.py` does not exist.

- [ ] **Step 4: Add factory composition helper**

Modify `backend/app/infrastructure/persistence/factory.py` imports to include:

```python
from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService
```

Add near the source/AI service builders:

```python
def build_source_to_insight_acceptance_service() -> SourceToInsightAcceptanceService:
    return SourceToInsightAcceptanceService(
        source_runtime=build_source_runtime_service(),
        reading=build_source_read_service(),
        complement=build_source_complement_service(),
        character_calibration=build_character_calibration_service(),
        knowledge=build_work_knowledge_service(),
        provider_platform=build_provider_platform_service(),
    )
```

- [ ] **Step 5: Implement the script**

Create `backend/scripts/smoke_source_to_insight.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run source-to-insight acceptance smoke.")
    parser.add_argument("--fixture-mode", action="store_true", help="Use bounded fixture inputs and deterministic services where configured.")
    parser.add_argument("--real-source-mode", action="store_true", help="Use configured repository/fetcher services against real sources.")
    parser.add_argument("--use-ai", action="store_true", help="Invoke provider only for compact analysis node.")
    parser.add_argument("--source-json", default="", help="Path to a Legado source JSON object or array.")
    parser.add_argument("--book-name", required=True)
    parser.add_argument("--author-hint", default="")
    parser.add_argument("--chapter-title", default="")
    parser.add_argument("--chapter-index", type=int, default=0)
    parser.add_argument("--source-limit", type=int, default=5)
    parser.add_argument("--actor-id", default="smoke")
    parser.add_argument("--output", default="backend/reports/source-to-insight-report.json")
    return parser.parse_args()


def load_source_records(path: str, limit: int) -> list[dict]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload if isinstance(payload, list) else [payload]
    return [item for item in records if isinstance(item, dict)][:limit]


async def main() -> int:
    args = parse_args()
    if args.fixture_mode and args.real_source_mode:
        raise SystemExit("--fixture-mode and --real-source-mode are mutually exclusive")

    from app.application.services.source_to_insight_acceptance_service import SourceToInsightScenario
    from app.infrastructure.persistence.factory import build_source_to_insight_acceptance_service

    service = build_source_to_insight_acceptance_service()
    scenario = SourceToInsightScenario(
        book_name=args.book_name,
        author_hint=args.author_hint,
        chapter_index=args.chapter_index,
        chapter_title=args.chapter_title,
        source_records=load_source_records(args.source_json, args.source_limit),
        source_json_path=args.source_json,
        source_limit=args.source_limit,
        use_ai=args.use_ai,
        actor_id=args.actor_id,
    )
    report = await service.run(scenario)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False))
    return 0 if report["status"] in {"passed", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 6: Run the script contract test**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_smoke_source_to_insight.py -q
```

Expected: PASS.

- [ ] **Step 7: Run the smoke script manually without AI**

Run from repository root:

```bash
cd backend && /tmp/legado-hub-pytest-venv/bin/python scripts/smoke_source_to_insight.py --fixture-mode --source-json tests/fixtures/source_to_insight_sources.json --book-name 斗罗大陆 --author-hint 唐家三少 --chapter-index 0 --output /tmp/source-to-insight-report.json
```

Expected: exit `0` and stdout JSON similar to:

```json
{"status":"passed","output":"/tmp/source-to-insight-report.json"}
```

If the status is `partial` because the fixture source cannot be fetched by real network-backed services, keep the script but adjust tests to use a smaller fake service seam in Task 4. Do not make network success required for unit tests.

- [ ] **Step 8: Commit Task 3**

```bash
git add backend/app/infrastructure/persistence/factory.py backend/scripts/smoke_source_to_insight.py backend/tests/fixtures/source_to_insight_sources.json backend/tests/test_smoke_source_to_insight.py
git commit -m "feat: add source insight smoke runner"
```

## Task 4: Optional Frontend Report Page

Implement this task only after backend Task 3 passes. Keep it minimal. This page starts a scenario and renders an existing report shape; it does not become an autonomous AI workbench.

**Files:**
- Create: `frontend/src/api/modules/sourceInsight.ts`
- Create: `frontend/src/features/novel/SourceInsightWorkbenchPage.tsx`
- Create: `frontend/src/features/novel/SourceInsightWorkbenchPage.test.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/app/navigation.tsx`

- [ ] **Step 1: Add the failing frontend page test**

Create `frontend/src/features/novel/SourceInsightWorkbenchPage.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

const sourceInsightMocks = vi.hoisted(() => ({
  runSourceInsightAcceptance: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: {
      status: 'passed',
      steps: [
        { name: 'search', status: 'passed', elapsed_ms: 12, summary: { keys: ['items'] }, errors: [] },
        { name: 'complement', status: 'passed', elapsed_ms: 18, summary: { successful_sources: 2 }, errors: [] },
      ],
      book_candidates: [{ source_id: 7, name: '斗罗大陆', sourceName: '源A', author: '唐家三少' }],
      complement: { successful_sources: 2, failed_sources: 0, final_content: '合并正文' },
      insights: {
        characters: ['唐三'],
        relations: [{ subject: '唐三', relation: 'appears_in', object_name: '第一章' }],
        plot_events: [{ event_title: '武魂觉醒', summary: '主角开始修炼' }],
        world_rules: [{ rule_name: '武魂规则', description: '每个人可觉醒武魂' }],
        timeline: [{ chapter_index: 0, title: '第一章', summary: '觉醒' }],
      },
      knowledge_proposals: [{ id: 'world-1', proposal_type: 'world_rule', status: 'candidate' }],
      ai: { used: false, status: 'skipped', provider: '', model: '', usage: {} },
    },
    meta: {},
    trace_id: null,
  }),
}))

vi.mock('@/api/modules/sourceInsight', () => sourceInsightMocks)

import { SourceInsightWorkbenchPage } from './SourceInsightWorkbenchPage'

test('source insight workbench runs scenario and renders distributed report', async () => {
  render(<SourceInsightWorkbenchPage />)

  fireEvent.change(screen.getByLabelText('书名'), { target: { value: '斗罗大陆' } })
  fireEvent.change(screen.getByLabelText('作者'), { target: { value: '唐家三少' } })
  fireEvent.click(screen.getByRole('button', { name: '运行验收' }))

  await waitFor(() => expect(sourceInsightMocks.runSourceInsightAcceptance).toHaveBeenCalledWith(expect.objectContaining({
    book_name: '斗罗大陆',
    author_hint: '唐家三少',
    use_ai: false,
  })))
  expect(await screen.findByText('passed')).toBeInTheDocument()
  expect(screen.getByText('唐三')).toBeInTheDocument()
  expect(screen.getByText('武魂规则')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the RED frontend test**

Run from `frontend/`:

```bash
npm test -- --run src/features/novel/SourceInsightWorkbenchPage.test.tsx
```

Expected: FAIL because `SourceInsightWorkbenchPage` and `sourceInsight` API module do not exist.

- [ ] **Step 3: Create the API module**

Create `frontend/src/api/modules/sourceInsight.ts`:

```ts
import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface SourceInsightScenarioRequest {
  book_name: string
  author_hint?: string
  chapter_title?: string
  chapter_index?: number
  source_limit?: number
  use_ai?: boolean
}

export interface SourceInsightReport {
  status: 'passed' | 'failed' | 'partial'
  steps: Array<{ name: string; status: string; elapsed_ms: number; summary: Record<string, unknown>; errors: string[] }>
  book_candidates: Array<Record<string, unknown>>
  complement: Record<string, unknown>
  insights: {
    characters: string[]
    relations: Array<Record<string, unknown>>
    plot_events: Array<Record<string, unknown>>
    world_rules: Array<Record<string, unknown>>
    timeline: Array<Record<string, unknown>>
  }
  knowledge_proposals: Array<Record<string, unknown>>
  ai: { used: boolean; status: string; provider: string; model: string; usage: Record<string, unknown> }
}

export function runSourceInsightAcceptance(payload: SourceInsightScenarioRequest): Promise<ApiEnvelope<SourceInsightReport>> {
  return apiClient.post('/reading/source-insight/acceptance', payload)
}
```

- [ ] **Step 4: Create the minimal page**

Create `frontend/src/features/novel/SourceInsightWorkbenchPage.tsx`:

```tsx
import { FormEvent, useState } from 'react'

import { runSourceInsightAcceptance, type SourceInsightReport } from '@/api/modules/sourceInsight'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

export function SourceInsightWorkbenchPage() {
  const [bookName, setBookName] = useState('')
  const [authorHint, setAuthorHint] = useState('')
  const [useAI, setUseAI] = useState(false)
  const [report, setReport] = useState<SourceInsightReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!bookName.trim()) return
    setLoading(true)
    setError('')
    setReport(null)
    try {
      const response = await runSourceInsightAcceptance({
        book_name: bookName.trim(),
        author_hint: authorHint.trim() || undefined,
        chapter_index: 0,
        source_limit: 5,
        use_ai: useAI,
      })
      setReport(response.data)
    } catch {
      setError('验收运行失败，请检查后端服务和权限。')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ConsoleLayout
      eyebrow="小说验收"
      title="写源到分析验收"
      description="按真实分散服务链路验证：书源、找书、目录、正文、多源互补、知识候选；AI 只作为可选分析节点。"
    >
      <form onSubmit={submit} className="grid gap-4 rounded-lg border border-border bg-card p-5 md:grid-cols-[1fr_1fr_auto]">
        <label className="grid gap-2 text-sm font-medium">
          书名
          <Input aria-label="书名" value={bookName} onChange={(event) => setBookName(event.target.value)} />
        </label>
        <label className="grid gap-2 text-sm font-medium">
          作者
          <Input aria-label="作者" value={authorHint} onChange={(event) => setAuthorHint(event.target.value)} />
        </label>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input type="checkbox" checked={useAI} onChange={(event) => setUseAI(event.target.checked)} />
          使用 AI 分析
        </label>
        <div className="md:col-span-3">
          <Button type="submit" disabled={loading || !bookName.trim()}>{loading ? '运行中' : '运行验收'}</Button>
        </div>
      </form>

      {error ? <p role="alert" className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p> : null}

      {report ? (
        <div className="grid gap-4">
          <Card className="p-5">
            <h2 className="text-lg font-semibold">验收状态</h2>
            <p className="mt-2 text-sm text-muted-foreground">{report.status}</p>
            <div className="mt-4 grid gap-2 md:grid-cols-3">
              {report.steps.map((step) => (
                <div key={step.name} className="rounded-md border border-border p-3 text-sm">
                  <p className="font-medium">{step.name}</p>
                  <p className={step.status === 'passed' ? 'text-emerald-600' : 'text-rose-600'}>{step.status} · {step.elapsed_ms}ms</p>
                </div>
              ))}
            </div>
          </Card>

          <Card className="grid gap-4 p-5 md:grid-cols-2">
            <section>
              <h2 className="text-lg font-semibold">人物与关系</h2>
              <div className="mt-3 flex flex-wrap gap-2">{report.insights.characters.map((item) => <span key={item} className="rounded-full bg-muted px-3 py-1 text-sm">{item}</span>)}</div>
              <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">{JSON.stringify(report.insights.relations, null, 2)}</pre>
            </section>
            <section>
              <h2 className="text-lg font-semibold">世界观与时间线</h2>
              <div className="mt-3 space-y-2 text-sm">
                {report.insights.world_rules.map((item, index) => <p key={index}>{String(item.rule_name ?? '')}</p>)}
              </div>
              <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">{JSON.stringify(report.insights.timeline, null, 2)}</pre>
            </section>
          </Card>
        </div>
      ) : null}
    </ConsoleLayout>
  )
}
```

- [ ] **Step 5: Register route and navigation**

Modify `frontend/src/app/router.tsx`:

```tsx
import { SourceInsightWorkbenchPage } from '@/features/novel/SourceInsightWorkbenchPage'
```

Add to `appRoutes`:

```tsx
{ path: '/novel/source-insight', element: <SourceInsightWorkbenchPage /> },
```

Add inside the authenticated route block under `novel.manage`:

```tsx
<Route element={<RequirePermission permission="novel.manage" />}>
  <Route path="/novel/tasks" element={<NovelTasksPage />} />
  <Route path="/novel/source-insight" element={<SourceInsightWorkbenchPage />} />
</Route>
```

Modify `frontend/src/app/navigation.tsx` in the operations or novel group:

```tsx
{ label: '写源验收', to: '/novel/source-insight', icon: ClipboardList, permission: 'novel.manage' }
```

- [ ] **Step 6: Run frontend tests**

Run:

```bash
npm test -- --run src/features/novel/SourceInsightWorkbenchPage.test.tsx src/app/router.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add frontend/src/api/modules/sourceInsight.ts frontend/src/features/novel/SourceInsightWorkbenchPage.tsx frontend/src/features/novel/SourceInsightWorkbenchPage.test.tsx frontend/src/app/router.tsx frontend/src/app/navigation.tsx
git commit -m "feat: add source insight acceptance page"
```

## Task 5: HTTP Endpoint for Frontend and Operator Runs

Only implement this if Task 4 is included. If the first delivery is CLI-only, skip this task and document that frontend wiring is deferred.

**Files:**
- Modify: `backend/app/interfaces/http/reading.py`
- Test: `backend/tests/test_api_source_to_insight_acceptance.py`

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/test_api_source_to_insight_acceptance.py`:

```python
from fastapi.testclient import TestClient


def test_source_insight_acceptance_endpoint_requires_novel_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-insight-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    denied = create_access_token({"sub": "1", "permissions": ["book_sources.read"], "roles": []})
    response = client.post(
      "/api/reading/source-insight/acceptance",
      headers={"Authorization": f"Bearer {denied}"},
      json={"book_name": "斗罗大陆", "author_hint": "唐家三少"},
    )
    assert response.status_code == 403
```

Append a monkeypatched happy path:

```python
def test_source_insight_acceptance_endpoint_returns_report(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-insight-api-ok.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    class FakeService:
        async def run(self, scenario):
            return {
                "scenario": {"book_name": scenario.book_name},
                "status": "passed",
                "steps": [],
                "book_candidates": [],
                "complement": {},
                "insights": {"characters": [], "relations": [], "plot_events": [], "world_rules": [], "timeline": []},
                "knowledge_proposals": [],
                "ai": {"used": False, "status": "skipped", "provider": "", "model": "", "usage": {}},
            }

    import app.interfaces.http.reading as reading_module

    monkeypatch.setattr(reading_module, "build_source_to_insight_acceptance_service", lambda: FakeService())

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token({"sub": "1", "permissions": ["novel.manage"], "roles": []})
    response = client.post(
        "/api/reading/source-insight/acceptance",
        headers={"Authorization": f"Bearer {token}"},
        json={"book_name": "斗罗大陆", "author_hint": "唐家三少", "use_ai": False},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "passed"
    assert response.json()["data"]["scenario"]["book_name"] == "斗罗大陆"
```

- [ ] **Step 2: Run the RED API tests**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_api_source_to_insight_acceptance.py -q
```

Expected: FAIL because `/api/reading/source-insight/acceptance` is not registered.

- [ ] **Step 3: Add endpoint models and route**

Modify `backend/app/interfaces/http/reading.py` imports:

```python
from app.application.services.source_to_insight_acceptance_service import SourceToInsightScenario
from app.infrastructure.persistence.factory import build_source_to_insight_acceptance_service
```

Add request model:

```python
class SourceInsightAcceptanceRequest(BaseModel):
    book_name: str
    author_hint: str = ""
    chapter_title: str = ""
    chapter_index: int = 0
    source_limit: int = 5
    use_ai: bool = False
```

Add route:

```python
@router.post("/source-insight/acceptance")
async def run_source_insight_acceptance(
    payload: SourceInsightAcceptanceRequest,
    identity=Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    service = build_source_to_insight_acceptance_service()
    data = await service.run(SourceToInsightScenario(
        book_name=payload.book_name,
        author_hint=payload.author_hint,
        chapter_title=payload.chapter_title,
        chapter_index=payload.chapter_index,
        source_limit=payload.source_limit,
        use_ai=payload.use_ai,
        actor_id=str(identity.user_id),
    ))
    return {
        "success": True,
        "code": "OK",
        "message": "source insight acceptance completed",
        "data": data,
        "meta": {"status": data["status"]},
        "trace_id": None,
    }
```

- [ ] **Step 4: Run API tests**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_api_source_to_insight_acceptance.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add backend/app/interfaces/http/reading.py backend/tests/test_api_source_to_insight_acceptance.py
git commit -m "feat: expose source insight acceptance endpoint"
```

## Task 6: Verification and Real Provider Smoke Preparation

**Files:**
- Modify only if a discovered bug is directly in the acceptance path.
- No new files expected.

- [ ] **Step 1: Run focused backend acceptance tests**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py tests/test_smoke_source_to_insight.py tests/test_source_read_service.py tests/test_source_complement_app_service.py tests/test_character_calibration_service.py tests/test_work_knowledge_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Run API tests if Task 5 was implemented**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_api_source_to_insight_acceptance.py tests/test_api_ai_workspace.py tests/test_api_provider_platform.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend tests if Task 4 was implemented**

Run:

```bash
cd frontend && npm test -- --run src/features/novel/SourceInsightWorkbenchPage.test.tsx src/app/router.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run deterministic smoke**

Run:

```bash
cd backend && /tmp/legado-hub-pytest-venv/bin/python scripts/smoke_source_to_insight.py --fixture-mode --source-json tests/fixtures/source_to_insight_sources.json --book-name 斗罗大陆 --author-hint 唐家三少 --chapter-index 0 --output /tmp/source-to-insight-report.json
```

Expected: exit `0`, report exists, and `ai.status` is `skipped`.

- [ ] **Step 5: Prepare real-provider command for user-supplied credentials**

Do not run this until the user supplies API URL/key or a configured provider account:

```bash
cd backend && /tmp/legado-hub-pytest-venv/bin/python scripts/smoke_source_to_insight.py --real-source-mode --source-json "../测试源/shareBookSource.json" --book-name "斗罗大陆" --author-hint "唐家三少" --chapter-index 0 --source-limit 5 --use-ai --output /tmp/source-to-insight-ai-report.json
```

Expected after credentials are configured in the environment or provider account table: exit `0` or partial only for source-site failures, `ai.used=true`, provider/model/usage recorded, and deterministic source steps visible in the report.

- [ ] **Step 6: Commit any verification-only fixes**

Only if fixes were needed:

```bash
git add backend/app/application/services/source_to_insight_acceptance_service.py backend/scripts/smoke_source_to_insight.py backend/app/interfaces/http/reading.py backend/tests/test_source_to_insight_acceptance_service.py backend/tests/test_smoke_source_to_insight.py backend/tests/test_api_source_to_insight_acceptance.py
git commit -m "fix: stabilize source insight acceptance smoke"
```

## Self-Review Checklist

- Spec coverage:
  - Deterministic source import/build selection: Task 1 and Task 3.
  - Source validation: Task 1.
  - Search/toc/content: Task 1.
  - Multi-source complement: Task 1.
  - Character/world/plot/timeline candidates: Task 1.
  - Optional AI analysis over compact evidence: Task 2.
  - Acceptance report: Task 1 and Task 3.
  - Frontend secondary page: Task 4.
  - Real-provider smoke after credentials: Task 6.
- Placeholder scan: no TBD/TODO placeholders are intentionally left in the plan.
- Dirty workspace handling: plan explicitly avoids staging CRLF-only drift and the large `shareBookSource.json` movement.
