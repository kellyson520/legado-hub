# Legado Runtime Source Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real source-runtime subsystem that versions source rules, executes high-compatibility Legado-style parsing against live book/RSS sources, persists diagnostics, and automates promotion/rollback.

**Architecture:** Extend the current `core / domain / application / infrastructure / interfaces` backend with a dedicated source-runtime persistence layer, rule-execution pipeline, adapter-based real test flows, and deployment-quality gate orchestration. Keep the authenticated main API under `app/interfaces/http/` as the only runtime surface.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, SQLite, aiohttp/httpx, BeautifulSoup, lxml, jsonpath-ng, pytest, pytest-asyncio

---

> **Git note:** this working copy currently has no `.git`. Replace each “Commit” step with a filesystem checkpoint under `docs/superpowers/reports/checkpoints/`.

## File Structure

```text
backend/app/
├── domain/
│   ├── entities/source_runtime.py                  # source definition/version/run/deployment objects
│   └── repositories/source_runtime_repo.py         # runtime persistence contract
├── application/services/
│   ├── source_runtime_service.py                   # generate/repair/regression/deploy orchestration
│   └── source_health_service.py                    # scheduled verification + rollback decisions
├── infrastructure/legado/engine/
│   ├── source_adapters.py                          # book/rss runtime flows
│   ├── quality_gate.py                             # promotion/quarantine/rollback decisions
│   ├── text_pipeline.py                            # regex/string transforms
│   ├── js_runtime.py                               # bounded JS sandbox
│   └── executor.py                                 # expanded selector execution
├── infrastructure/persistence/sqlite/
│   ├── schema.py                                   # runtime tables
│   └── source_runtime_repo_impl.py                 # SQLite implementation
├── interfaces/http/
│   ├── engine.py                                   # runtime endpoints
│   └── sources.py                                  # version/history endpoints
└── tasks/scheduler.py                              # recurring health verification
backend/tests/
├── test_source_runtime_repo.py
├── test_engine_selector_pipeline.py
├── test_source_adapters.py
├── test_engine_runtime_service.py
├── test_api_engine_runtime.py
└── test_source_health_scheduler.py
```

### Task 1: Add source runtime persistence backbone

**Files:**
- Create: `backend/app/domain/entities/source_runtime.py`
- Create: `backend/app/domain/repositories/source_runtime_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Create: `backend/app/infrastructure/persistence/sqlite/source_runtime_repo_impl.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_source_runtime_repo.py`

- [ ] **Step 1: Write the failing test**

```python
from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository


def test_create_candidate_version_and_run_record(sqlite_session):
    repo = SQLiteSourceRuntimeRepository(sqlite_session)
    version = repo.create_candidate_version(
        source_type="book",
        source_id="source-1",
        payload={"ruleSearch": {"bookList": ".book"}},
        created_by="admin",
    )
    run = repo.record_test_run(
        source_version_id=version.id,
        trigger="manual",
        score=92,
        grade="A",
        step_results={"search": {"passed": True, "elapsed_ms": 120}},
    )

    assert version.status == "candidate"
    assert run.step_results["search"]["passed"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_source_runtime_repo.py::test_create_candidate_version_and_run_record -v`  
Expected: FAIL with `ModuleNotFoundError` or missing repository methods.

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class SourceVersion:
    id: str
    source_type: str
    source_id: str
    status: str
    payload: dict
    created_by: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class SourceTestRun:
    id: str
    source_version_id: str
    trigger: str
    score: int
    grade: str
    step_results: dict
    created_at: datetime = field(default_factory=datetime.utcnow)
```

```python
class SQLiteSourceRuntimeRepository(SourceRuntimeRepository):
    def create_candidate_version(self, source_type: str, source_id: str, payload: dict, created_by: str) -> SourceVersion:
        version = SourceVersion(id=uuid4().hex, source_type=source_type, source_id=source_id, status="candidate", payload=payload, created_by=created_by)
        self.session.add(SourceVersionModel.from_entity(version))
        self.session.commit()
        return version

    def record_test_run(self, source_version_id: str, trigger: str, score: int, grade: str, step_results: dict) -> SourceTestRun:
        run = SourceTestRun(id=uuid4().hex, source_version_id=source_version_id, trigger=trigger, score=score, grade=grade, step_results=step_results)
        self.session.add(SourceTestRunModel.from_entity(run))
        self.session.commit()
        return run
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_source_runtime_repo.py::test_create_candidate_version_and_run_record -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `New-Item -ItemType Directory -Force docs/superpowers/reports/checkpoints | Out-Null; Copy-Item backend/app/domain/entities/source_runtime.py docs/superpowers/reports/checkpoints/2026-07-07-source-runtime-task1.py`  
Expected: checkpoint file exists.

### Task 2: Expand selector execution, text transforms, and JS sandbox

**Files:**
- Modify: `backend/app/infrastructure/legado/engine/parser.py`
- Modify: `backend/app/infrastructure/legado/engine/executor.py`
- Modify: `backend/app/infrastructure/legado/engine/models.py`
- Modify: `backend/app/infrastructure/legado/engine/text_pipeline.py`
- Modify: `backend/app/infrastructure/legado/engine/js_runtime.py`
- Test: `backend/tests/test_engine_selector_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
from app.infrastructure.legado.engine.harness import run_rule_harness


def test_harness_executes_regex_and_replace_chain():
    result = run_rule_harness("@css:.title##(.*)##$1@replace:Foo=>Bar", "<div class='title'>Foo Story</div>")
    assert result.execution.values == ["Bar Story"]


def test_harness_executes_js_with_timeout_guard():
    result = run_rule_harness("@js:return ['ok']", {"items": []})
    assert result.success is True
    assert result.execution.values == ["ok"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_engine_selector_pipeline.py -v`  
Expected: FAIL because regex/text chain and JS execution are not fully implemented.

- [ ] **Step 3: Write minimal implementation**

```python
def apply_text_pipeline(values: list[str], operations: list[dict]) -> list[str]:
    current = values
    for operation in operations:
        if operation["kind"] == "replace":
            current = [value.replace(operation["old"], operation["new"]) for value in current]
        elif operation["kind"] == "regex":
            current = run_regex_extract(current, operation["pattern"], operation.get("group", 0))
    return [value.strip() for value in current if value]
```

```python
def execute_js_rule(source: dict | str, script: str) -> list[str]:
    runtime = build_js_runtime(timeout_ms=200)
    return runtime.run(script=script, payload=source)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_engine_selector_pipeline.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/infrastructure/legado/engine/executor.py docs/superpowers/reports/checkpoints/2026-07-07-source-runtime-task2.py`  
Expected: checkpoint file exists.

### Task 3: Implement book/RSS adapters and real run diagnostics

**Files:**
- Create: `backend/app/infrastructure/legado/engine/source_adapters.py`
- Modify: `backend/app/infrastructure/legado/engine/http_client.py`
- Modify: `backend/app/application/services/engine_service.py`
- Test: `backend/tests/test_source_adapters.py`

- [ ] **Step 1: Write the failing tests**

```python
from app.infrastructure.legado.engine.source_adapters import BookSourceAdapter, RssSourceAdapter


async def test_book_adapter_records_search_toc_and_content_steps(fake_http_runtime):
    adapter = BookSourceAdapter(fake_http_runtime)
    result = await adapter.run(
        source={"searchUrl": "https://example.com?q={{keyword}}", "ruleSearch": {"bookList": ".book", "name": ".name"}},
        keyword="demo",
    )
    assert list(result.step_results) == ["search", "toc", "content"]
    assert result.step_results["search"]["passed"] is True


async def test_rss_adapter_records_feed_steps(fake_http_runtime):
    adapter = RssSourceAdapter(fake_http_runtime)
    result = await adapter.run(source={"sourceUrl": "https://example.com/feed.xml", "ruleArticles": "item"})
    assert result.step_results["feed_fetch"]["passed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_source_adapters.py -v`  
Expected: FAIL because adapters do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
class BookSourceAdapter:
    async def run(self, source: dict, keyword: str) -> RuntimeExecutionSummary:
        search_step = await self._run_search(source, keyword)
        toc_step = await self._run_toc(source, search_step)
        content_step = await self._run_content(source, toc_step)
        return RuntimeExecutionSummary(step_results={"search": search_step, "toc": toc_step, "content": content_step})


class RssSourceAdapter:
    async def run(self, source: dict) -> RuntimeExecutionSummary:
        feed_step = await self._run_feed_fetch(source)
        items_step = self._run_item_parse(source, feed_step)
        return RuntimeExecutionSummary(step_results={"feed_fetch": feed_step, "item_parse": items_step})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_source_adapters.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/infrastructure/legado/engine/source_adapters.py docs/superpowers/reports/checkpoints/2026-07-07-source-runtime-task3.py`  
Expected: checkpoint file exists.

### Task 4: Orchestrate generate/repair/regression/deploy APIs

**Files:**
- Create: `backend/app/application/services/source_runtime_service.py`
- Modify: `backend/app/application/services/engine_service.py`
- Modify: `backend/app/interfaces/http/engine.py`
- Modify: `backend/app/interfaces/http/sources.py`
- Test: `backend/tests/test_engine_runtime_service.py`
- Test: `backend/tests/test_api_engine_runtime.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_runtime_service_promotes_candidate_after_clean_regression(runtime_service, runtime_repo):
    candidate = await runtime_service.generate({"url": "https://example.com", "source_type": "book"}, actor_id="admin")
    decision = await runtime_service.deploy(candidate["source_version_id"], actor_id="admin")
    assert decision["status"] == "published"
    assert decision["quality_gate"]["allowed"] is True
```

```python
def test_engine_api_exposes_runs_and_deployments(client, admin_headers):
    response = client.get("/api/engine/runs", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_engine_runtime_service.py backend/tests/test_api_engine_runtime.py -v`  
Expected: FAIL because orchestration and endpoints are missing.

- [ ] **Step 3: Write minimal implementation**

```python
class SourceRuntimeService:
    async def generate(self, payload: dict, actor_id: str) -> dict:
        version = self.repo.create_candidate_version(source_type=payload["source_type"], source_id=payload["url"], payload={"generated_from": payload["url"]}, created_by=actor_id)
        return {"source_version_id": version.id, "status": version.status}

    async def repair(self, source_version_id: str, actor_id: str) -> dict:
        repaired = self.repairer.repair_version(self.repo.get_version(source_version_id))
        return self.repo.save_repaired_version(source_version_id, repaired, actor_id)

    async def regression(self, source_version_id: str, actor_id: str) -> dict:
        candidate = self.repo.get_version(source_version_id)
        baseline = self.repo.get_current_published_version(candidate.source_type, candidate.source_id)
        return self.quality_gate.compare_candidate(candidate, baseline)

    async def deploy(self, source_version_id: str, actor_id: str) -> dict:
        decision = await self.regression(source_version_id, actor_id)
        return self.repo.apply_deployment_decision(source_version_id, decision, actor_id)
```

```python
@router.post("/deploy")
async def deploy(payload: DeployRequest, identity: RequestIdentity = Depends(get_current_identity), _=Depends(require_permission(Permission.ENGINE_DEPLOY))):
    service = build_source_runtime_service()
    data = await service.deploy(payload.source_version_id, identity.user_id)
    return {"success": True, "code": "OK", "message": "deployment decision computed", "data": data, "meta": {}, "trace_id": None}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_engine_runtime_service.py backend/tests/test_api_engine_runtime.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/interfaces/http/engine.py docs/superpowers/reports/checkpoints/2026-07-07-source-runtime-task4.py`  
Expected: checkpoint file exists.

### Task 5: Add scheduled health checks, quarantine, rollback, and real-source regression suite

**Files:**
- Create: `backend/app/application/services/source_health_service.py`
- Modify: `backend/app/tasks/scheduler.py`
- Modify: `backend/app/infrastructure/legado/engine/quality_gate.py`
- Test: `backend/tests/test_source_health_scheduler.py`
- Test: `backend/tests/test_real_source_smoke.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_health_service_quarantines_and_rolls_back_unstable_version(source_health_service, seeded_runtime_repo):
    result = await source_health_service.verify_published_versions()
    assert result[0]["action"] == "rollback"
    assert result[0]["new_status"] == "rolled_back"
```

```python
async def test_real_source_smoke_suite_returns_structured_failures(real_source_smoke_runner):
    summary = await real_source_smoke_runner.run_all()
    assert "book" in summary["by_type"]
    assert "rss" in summary["by_type"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_source_health_scheduler.py backend/tests/test_real_source_smoke.py -v`  
Expected: FAIL because rollback scheduler and smoke runner are missing.

- [ ] **Step 3: Write minimal implementation**

```python
class SourceHealthService:
    async def verify_published_versions(self) -> list[dict]:
        decisions = []
        for version in self.repo.list_published_versions():
            run = await self.runtime.verify_version(version)
            decision = self.quality_gate.evaluate_runtime_health(version, run)
            if decision.action in {"quarantine", "rollback"}:
                self.repo.apply_health_decision(version.id, decision)
            decisions.append(decision.to_dict())
        return decisions
```

```python
async def run_source_runtime_health_job() -> None:
    service = build_source_health_service()
    await service.verify_published_versions()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_source_health_scheduler.py backend/tests/test_real_source_smoke.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/tasks/scheduler.py docs/superpowers/reports/checkpoints/2026-07-07-source-runtime-task5.py`  
Expected: checkpoint file exists.
