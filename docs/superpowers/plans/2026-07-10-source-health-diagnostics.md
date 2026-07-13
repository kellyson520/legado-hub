# Source Health Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make source-health failures explainable and provide an operational per-source diagnostics page backed by persisted probe history.

**Architecture:** Retain `SourceProbeService` as the producer of safe per-stage evidence and classify that evidence in `SourceHealthClassifierService`. Reuse the existing `source_probe_runs` JSON columns and detail endpoint, then add a strongly typed React detail route that renders current route policy, request/response summaries, run history, and failure events.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy/SQLite, pytest, React 18, TypeScript, React Router, Vitest, Testing Library, Tailwind, lucide-react.

---

## Sync Status (2026-07-11)

> Sync note: 下方 checkbox 保留原始实施脚本；当前执行状态以本节为准。

- **Overall:** 计划已完成；`2026-07-10` 的实源探测 checkpoint 仍然有效，本次同步重新验证了后端回归、前端测试与生产构建。
- **Verification:**
  - `backend/.venv/Scripts/python.exe -m pytest tests/test_source_health_classifier_service.py tests/test_source_probe_service.py tests/test_source_health_admin_service.py tests/test_source_health_repo.py tests/test_source_routing_service.py tests/test_api_source_health.py -q` → `17 passed`
  - `npm test -- --run src/features/sources/SourceHealthPage.test.tsx src/features/sources/SourceHealthDetailPage.test.tsx` → `2 files passed`
  - `npm run build` → pass
  - Checkpoint evidence: `docs/superpowers/reports/checkpoints/2026-07-10-source-health-diagnostics.md`

| Task | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Task 1 | 完成 | `test_source_health_classifier_service.py` 通过 | 四类目标诊断与优先级分支已落地。 |
| Task 2 | 完成 | `test_source_probe_service.py` 通过 | 搜索 / TOC / Content 安全诊断与脱敏预览已统一。 |
| Task 3 | 完成 | `test_source_health_admin_service.py`、`test_api_source_health.py` 通过 | 详情接口已返回 `route_decision` 与 `failure_timeline`。 |
| Task 4 | 完成 | `SourceHealthDetailPage.test.tsx` 通过 | 前端详情页、路由与 API 类型已落地。 |
| Task 5 | 完成 | `SourceHealthPage.test.tsx` 通过 | 健康列表已可跳转单源详情。 |
| Task 6 | 完成 | checkpoint 报告已存在，且本次回归/构建复验通过 | `2026-07-10` 的实源复探结果已写入报告；本次同步未重跑同一批实源。 |

## File Structure

- Modify: `backend/app/application/services/source_health_classifier_service.py` - ordered diagnostic categorization and corresponding health/confidence policy.
- Modify: `backend/app/application/services/source_probe_service.py` - consistently capture safe diagnostics for search, toc, and content empty/failure cases.
- Modify: `backend/app/application/services/source_health_admin_service.py` - return presentation-ready route decision and sanitized histories.
- Modify: `backend/app/interfaces/http/source_health.py` - keep the existing detail route contract explicit.
- Modify: `backend/tests/test_source_health_classifier_service.py` - classifier precedence coverage.
- Modify: `backend/tests/test_source_probe_service.py` - stage evidence and preview safety coverage.
- Modify: `backend/tests/test_source_health_admin_service.py` and `backend/tests/test_api_source_health.py` - detail payload and API contract coverage.
- Modify: `frontend/src/api/modules/sourceHealth.ts` - detail, probe-run, route-decision types and `getSourceHealth` request.
- Create: `frontend/src/features/sources/SourceHealthDetailPage.tsx` - detail surface and timeline.
- Create: `frontend/src/features/sources/SourceHealthDetailPage.test.tsx` - data, history, empty-state, and route control coverage.
- Modify: `frontend/src/features/sources/SourceHealthPage.tsx` and `frontend/src/features/sources/SourceHealthPage.test.tsx` - detail link from health list.
- Modify: `frontend/src/app/router.tsx` - `/sources/health/:sourceId` route.
- Create: `docs/superpowers/reports/checkpoints/2026-07-10-source-health-diagnostics.md` - verified real-source results.

### Task 1: Specify And Implement Failure Categories

**Files:**
- Modify: `backend/tests/test_source_health_classifier_service.py`
- Modify: `backend/app/application/services/source_health_classifier_service.py`

- [ ] **Step 1: Add failing classifier tests for the four target categories**

```python
def test_classifier_marks_non_waf_http_status_as_http_status_error():
    decision = SourceHealthClassifierService().classify(_evidence(
        StageProbeResult(stage="search", status="failed", detail={"http_status": 503, "response_kind": "html"})
    ))
    assert decision.failure_reason == "http_status_error"
    assert decision.health_status == "blocked"

def test_classifier_marks_html_response_for_json_rule_as_html_instead_of_json():
    decision = SourceHealthClassifierService().classify(_evidence(
        StageProbeResult(stage="search", status="failed", detail={"http_status": 200, "response_kind": "html", "expected_response_kind": "json"})
    ))
    assert decision.failure_reason == "html_instead_of_json"
    assert decision.health_status == "degraded"

def test_classifier_marks_successful_empty_parse_as_parse_empty():
    decision = SourceHealthClassifierService().classify(_evidence(
        StageProbeResult(stage="search", status="failed", detail={"http_status": 200, "response_kind": "json", "parse_status": "empty"})
    ))
    assert decision.failure_reason == "parse_empty"
```

- [ ] **Step 2: Run the focused classifier test file and confirm the new tests fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_source_health_classifier_service.py -q`

Expected: the three new assertions fail because the classifier still emits `http_error`, `unknown_error`, or another existing category.

- [ ] **Step 3: Implement ordered, evidence-based branches**

```python
http_status = int(stage.detail.get("http_status") or 0)
response_kind = str(stage.detail.get("response_kind") or "").lower()
expected_kind = str(stage.detail.get("expected_response_kind") or "").lower()
parse_status = str(stage.detail.get("parse_status") or "").lower()

if http_status in {403, 429} or any(marker in lowered for marker in WAF_MARKERS):
    return "waf_blocked"
if http_status >= 400:
    return "http_status_error"
if http_status and response_kind == "html" and expected_kind == "json":
    return "html_instead_of_json"
if http_status and parse_status == "empty":
    return "parse_empty"
```

Update `_health_status`, `_confidence`, and `_next_probe_minutes` so `http_status_error` is `blocked`, while `html_instead_of_json` is `degraded` with medium confidence. Retain `unknown_error` only after all stage evidence has been examined.

- [ ] **Step 4: Run classifier tests and confirm they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_source_health_classifier_service.py -q`

Expected: all classifier tests pass.

### Task 2: Produce Safe, Uniform Stage Diagnostics

**Files:**
- Modify: `backend/tests/test_source_probe_service.py`
- Modify: `backend/app/application/services/source_probe_service.py`

- [ ] **Step 1: Add failing evidence tests for empty toc/content and secret redaction**

```python
assert probe.toc.detail["parse_status"] == "empty"
assert probe.toc.detail["expected_response_kind"] == "json"
assert "Cookie" not in probe.search.request_preview
assert "Authorization" not in probe.search.request_preview
```

Use a fake configured request returning `HttpResponse(status=200, is_html=True, text="<html>challenge</html>")` to assert `response_kind == "html"`, a truncated preview, and `expected_response_kind == "json"`.

- [ ] **Step 2: Run the probe-service test file and confirm the added tests fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_source_probe_service.py -q`

Expected: missing `parse_status`/`expected_response_kind` keys or an unsanitized preview assertion failure.

- [ ] **Step 3: Add a shared stage-diagnostic helper and use it in search, toc, and content paths**

```python
def _safe_preview(self, text: str) -> str:
    return re.sub(r"(?i)(cookie|authorization)\\s*[:=]\\s*[^;\\s]+", r"\\1=[redacted]", text or "")[:300]

def _response_diagnostics(self, response, *, parse_status: str = "unknown") -> dict:
    return {
        "http_status": response.status,
        "http_error": response.error or "",
        "response_kind": "json" if response.is_json else ("html" if response.is_html else "text"),
        "response_preview": self._safe_preview(response.text),
        "expected_response_kind": "json",
        "parse_status": parse_status,
        "http_elapsed_ms": response.elapsed_ms,
    }
```

Attach `parse_status="empty"` whenever a completed fetch returns no parsed books, chapters, or body. Preserve JS metadata and request previews without headers.

- [ ] **Step 4: Run probe-service tests and confirm they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_source_probe_service.py -q`

Expected: all probe-service tests pass.

### Task 3: Expose Detail And Timeline Data

**Files:**
- Modify: `backend/tests/test_source_health_admin_service.py`
- Modify: `backend/tests/test_api_source_health.py`
- Modify: `backend/app/application/services/source_health_admin_service.py`
- Modify: `backend/app/interfaces/http/source_health.py`

- [ ] **Step 1: Add failing detail service and endpoint tests**

```python
detail = await service.get_book_source_health(created["id"])
assert detail["route_decision"] == {"policy": "skip", "score": 0.0, "reason": "waf_blocked"}
assert detail["failure_timeline"][0]["stage"] == "search"

response = client.get(f"/api/source-health/book-sources/{source_id}", headers=auth_headers)
assert response.json()["data"]["runs"][0]["search_result"]["detail"]["http_status"] == 403
```

- [ ] **Step 2: Run focused service and API tests and confirm they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_source_health_admin_service.py tests/test_api_source_health.py -q`

Expected: missing `route_decision` or `failure_timeline` keys.

- [ ] **Step 3: Build presentation data from persisted snapshots and runs**

```python
def _route_decision(snapshot):
    if snapshot is None:
        return {"policy": "probe_only", "score": 10.0, "reason": "not_probed"}
    return {"policy": snapshot.route_policy, "score": snapshot.route_score, "reason": snapshot.failure_reason}

def _failure_timeline(runs):
    return [
        {"at": run["created_at"], "stage": stage, "status": result["status"], "reason": run["failure_reason"], "message": result.get("error_message", "")}
        for run in runs for stage, result in (("search", run["search_result"]), ("toc", run["toc_result"]), ("content", run["content_result"]))
        if result.get("status") in {"failed", "degraded"}
    ]
```

Extend `get_book_source_health` with these keys while keeping `snapshot` and `runs` unchanged. The existing FastAPI handler continues to envelope that service payload.

- [ ] **Step 4: Run service and API tests and confirm they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_source_health_admin_service.py tests/test_api_source_health.py -q`

Expected: all selected tests pass.

### Task 4: Implement Source Detail API Client And Page

**Files:**
- Modify: `frontend/src/api/modules/sourceHealth.ts`
- Create: `frontend/src/features/sources/SourceHealthDetailPage.tsx`
- Create: `frontend/src/features/sources/SourceHealthDetailPage.test.tsx`
- Modify: `frontend/src/app/router.tsx`

- [ ] **Step 1: Add a failing page test with a mocked detail payload**

```tsx
expect(await screen.findByText('Route decision')).toBeInTheDocument()
expect(screen.getByText('waf_blocked')).toBeInTheDocument()
expect(screen.getByText('Failure timeline')).toBeInTheDocument()
expect(screen.getByText('https://example.test/search')).toBeInTheDocument()
```

Mock `getSourceHealth(67)` with a snapshot, one failed search run containing request/response previews, `route_decision`, and one timeline event. Add an empty-history test that asserts `No probe history`.

- [ ] **Step 2: Run the detail-page test and confirm it fails because the module is absent**

Run: `npm test -- --run src/features/sources/SourceHealthDetailPage.test.tsx`

Expected: FAIL with module-not-found or missing route/page export.

- [ ] **Step 3: Define client types and implement the detail route**

```ts
export interface SourceHealthDetail {
  snapshot: SourceHealthRow | null
  runs: SourceProbeRun[]
  route_decision: { policy: string; score: number; reason: string }
  failure_timeline: SourceFailureEvent[]
}

export async function getSourceHealth(sourceId: number) {
  return apiClient.get<SourceHealthDetail>(`/source-health/book-sources/${sourceId}`)
}
```

Use `useParams` to load the detail, render stable sections for the header, route decision, latest request/response preview, probe history, and failure timeline. Use `Eye`, `RefreshCw`, and `ArrowLeft` from `lucide-react` in the action controls, with `title` attributes. Add `<Route path="/sources/health/:sourceId" element={<SourceHealthDetailPage />} />`.

- [ ] **Step 4: Run the detail-page test and confirm it passes**

Run: `npm test -- --run src/features/sources/SourceHealthDetailPage.test.tsx`

Expected: all detail-page tests pass.

### Task 5: Link The Health List To Detail

**Files:**
- Modify: `frontend/src/features/sources/SourceHealthPage.tsx`
- Modify: `frontend/src/features/sources/SourceHealthPage.test.tsx`

- [ ] **Step 1: Add a failing health-list test for the per-source detail link**

```tsx
expect(await screen.findByRole('link', { name: 'View source details' })).toHaveAttribute('href', '/sources/health/7')
```

- [ ] **Step 2: Run the existing health page test and confirm it fails**

Run: `npm test -- --run src/features/sources/SourceHealthPage.test.tsx`

Expected: FAIL because the list does not render the detail link.

- [ ] **Step 3: Add an accessible icon link next to probe and recover controls**

```tsx
<Link to={`/sources/health/${row.source_id}`} title="View source details" aria-label="View source details">
  <Eye className="h-4 w-4" aria-hidden="true" />
</Link>
```

Use the existing list visual language without adding nested cards or changing the list API.

- [ ] **Step 4: Run the list test and frontend production build**

Run: `npm test -- --run src/features/sources/SourceHealthPage.test.tsx && npm run build`

Expected: selected test passes and Vite build completes without TypeScript errors.

### Task 6: Regression And Real-Source Probe

**Files:**
- Create: `docs/superpowers/reports/checkpoints/2026-07-10-source-health-diagnostics.md`

- [ ] **Step 1: Run the full source-health backend regression set**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_source_health_classifier_service.py tests/test_source_probe_service.py tests/test_source_health_admin_service.py tests/test_source_health_repo.py tests/test_source_routing_service.py tests/test_api_source_health.py -q`

Expected: all selected tests pass.

- [ ] **Step 2: Run all source-health frontend tests and build**

Run: `npm test -- --run src/features/sources/SourceHealthPage.test.tsx src/features/sources/SourceHealthDetailPage.test.tsx && npm run build`

Expected: all selected tests pass and the build completes.

- [ ] **Step 3: Re-probe the requested real sources**

Run: `./.venv/Scripts/python.exe scripts/probe_source_health.py --source-ids 30 67 108 --keywords 捞尸人 斗罗大陆 --probe-mode full_chain`

Expected: one persisted result for each source. The report records the status, per-stage outcomes, category, route policy, and safe evidence preview; an upstream failure is acceptable only when classified from evidence rather than left as an unexplained `unknown_error`.

- [ ] **Step 4: Write the checkpoint report with exact command output and classifications**

Use headings `Verification`, `Real-source results`, and `Residual unknown_error cases`. Include source IDs, observed categories, and why any remaining unknown result lacks enough evidence. Do not include cookies, authorization headers, or full response bodies.

## Completion Notes

This workspace has no Git repository at `C:\Users\lihuo\Desktop\legado-hub`, so no commit step is possible. Do not initialize a repository or alter Git configuration as part of this work.
