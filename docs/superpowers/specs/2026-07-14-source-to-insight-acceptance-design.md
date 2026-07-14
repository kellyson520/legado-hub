# Source to Insight Acceptance Design

## Context

Legado Hub already has the main building blocks for source import/build, source validation, reading search, table-of-contents loading, chapter content loading, source complement, character calibration, work knowledge proposals, and AI workspace calls. The missing piece is not a new autonomous agent that owns the whole flow. The missing piece is a repeatable acceptance path that proves these existing capabilities work together under the way the product will actually be used: separate API/service calls, with AI invoked only where analysis benefits from model reasoning.

The acceptance path must be able to run without a live provider by using deterministic fakes, then run again with a real OpenAI-compatible provider after credentials are supplied. The real-provider run should spend tokens only on the analysis node, not on search, crawling, complement, or orchestration.

## Goals

1. Verify a complete source-to-insight path in realistic service order:
   source import/build -> source validation -> book search -> toc -> chapter content -> multi-source complement -> character/world/plot/timeline insight candidates.
2. Keep source operations deterministic and inspectable. AI should not decide which endpoint to call for basic crawling or source selection in the default acceptance run.
3. Use AI sparingly for narrative analysis over compact evidence packets.
4. Produce an acceptance report with inputs, selected sources, outputs, errors, timings, provider usage, and proposal identifiers.
5. Preserve existing user work in the dirty checkout and avoid committing line-ending-only drift or large fixture movement.

## Non-Goals

1. Do not build an autonomous all-purpose agent that controls the whole application.
2. Do not send full books or large chapter batches into a model prompt.
3. Do not automatically publish source versions or knowledge proposals. Acceptance creates candidates and reports their review state.
4. Do not solve every weak source rule or every site-specific selector problem in this pass.

## Existing Capabilities Used

- `SourceRuntimeService`: imports Legado source JSON, creates candidate source versions, validates and publishes source versions.
- `SourceReadService`: searches books, loads toc, and loads chapter content with routing fallback.
- `SourceComplementAppService`: merges same-chapter content across multiple source candidates.
- `CharacterCalibrationService`: extracts character candidates and pairwise overlap from evidence, optionally using AI.
- `WorkKnowledgeService`: creates candidate relation, plot event, and world rule proposals.
- `ProviderPlatformService`: invokes OpenAI-compatible providers through configured provider groups.
- HTTP APIs under `/api/sources`, `/api/reading`, `/api/work-knowledge`, and `/api/ai`.

## Proposed Shape

### Real Source Targets

The first real-source acceptance run should use these operator-provided sites:

- `https://www.biquga.com/list/0/1.html`
- `https://www.beiquge.com/rank/`
- `https://m.biqugen.com/`
- `https://www.bqg39.cc/`

These URLs are not hand-authored into final Legado source rules. They are submitted to the existing source-writing engine first. The acceptance run measures whether the engine can inspect the site, generate a candidate source rule, and produce enough search/toc/content behavior for downstream reading tests.

### 1. Acceptance Runner

Add a backend acceptance runner that can be invoked as a script and covered by tests:

- Script: `backend/scripts/smoke_source_to_insight.py`
- Service: `backend/app/application/services/source_to_insight_acceptance_service.py`
- Tests:
  - `backend/tests/test_source_to_insight_acceptance_service.py`
  - `backend/tests/test_smoke_source_to_insight.py`

The runner accepts a small scenario:

```json
{
  "book_name": "斗罗大陆",
  "author_hint": "唐家三少",
  "chapter_index": 0,
  "chapter_title": "第一章",
  "source_urls": [
    "https://www.biquga.com/list/0/1.html",
    "https://www.beiquge.com/rank/",
    "https://m.biqugen.com/",
    "https://www.bqg39.cc/"
  ],
  "source_limit": 5,
  "use_ai": false
}
```

The default path uses existing services directly. It does not ask an LLM to choose tools for search, toc, content, or complement.

### 2. Deterministic Pipeline

The acceptance service runs these deterministic steps:

1. Submit URLs to the source-writing engine.
   - Call `SourceBuildService.submit()` for each `source_url`.
   - Process the resulting `source.build` jobs through `SourceBuildRuntimeService.handle_job()` or the existing job worker handler.
   - Record source version ids, job ids, agent run ids, source.inspect evidence, rule.validate/review.request decisions, and `autonomous_build` payloads.
   - If a URL times out or is blocked during probe, keep it in the report as a failed source-build target instead of hiding it.

2. Validate source candidates.
   - Run existing source validation against the engine-generated candidate rule.
   - Keep validation results in the report.
   - Do not publish automatically.

3. Search by book name.
   - Call `SourceReadService.search_books()`.
   - Prefer engine-generated candidates whose autonomous build decision is `canary`, then fall back to candidates that reached review with usable partial evidence.
   - Use source health/routing if available.
   - Keep the top candidates with source id, source name, source URL, book URL, author, and route decision.

4. Load toc from selected candidates.
   - Call `SourceReadService.get_book_toc()` for the best candidates.
   - Select a target chapter by `chapter_index` first, then by title similarity.

5. Load chapter content.
   - Call `SourceReadService.get_chapter_content()` for selected chapter candidates.
   - Keep content in storage/report, but create a compact `evidence_packet` for analysis.

6. Run multi-source complement.
   - Call `SourceComplementAppService.complement_chapter_candidates()`.
   - Record final content, successful source count, failed source count, merged-from source URLs, and per-source errors.

7. Run deterministic insight extraction.
   - Call `CharacterCalibrationService.calibrate()` with excerpts.
   - Create draft evidence fields for:
     - character candidates
     - relation candidates
     - plot event candidates
     - world rule candidates
     - timeline candidates
   - Timeline can be a first-pass deterministic list of chapter-indexed event summaries.

8. Create reviewable knowledge proposals.
   - Use `WorkKnowledgeService` to create candidate relation, plot event, and world rule proposals from compact evidence.
   - Do not publish them.

### 3. Optional AI Analysis Node

When `use_ai=true` and provider credentials are configured, invoke AI only after deterministic evidence is prepared.

The AI prompt receives:

- book title and author hint
- selected chapter title/index
- 1-3 short evidence excerpts
- complement summary
- character candidates
- explicit output schema request

The model output should be normalized into:

```json
{
  "characters": [],
  "relations": [],
  "plot_events": [],
  "world_rules": [],
  "timeline": [],
  "confidence": "low|medium|high",
  "notes": ""
}
```

The AI node must record:

- provider name
- model
- usage
- prompt evidence byte/character count
- sanitized raw output
- whether fallback deterministic analysis was used

If AI fails, the acceptance run still succeeds or fails based on deterministic steps. The report marks AI as failed and keeps the deterministic insight candidates.

### 4. Token and Tool-Call Discipline

The acceptance design treats regular services as tools in the engineering sense, but avoids model-driven tool calls for deterministic work. This saves tokens and makes failures easier to diagnose.

If later we add model tool-calling inside the analysis node, the allowed tool calls should be read-only and bounded:

- `get_evidence_packet`
- `get_chapter_excerpt`
- `get_complement_summary`
- `get_character_candidates`

The AI should not call source import, source publish, source build, arbitrary HTTP, or code execution tools.

### 5. Acceptance Report

The runner writes a JSON report under `backend/reports/` or a caller-provided output path. The report contains:

```json
{
  "scenario": {},
  "status": "passed|failed|partial",
  "steps": [
    {
      "name": "search",
      "status": "passed",
      "elapsed_ms": 123,
      "summary": {},
      "errors": []
    }
  ],
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
    "timeline": []
  },
  "knowledge_proposals": [],
  "ai": {
    "used": false,
    "status": "skipped",
    "provider": "",
    "model": "",
    "usage": {}
  }
}
```

The report is the source of truth for whether the distributed product flow works. It should be readable even when one step partially fails.

## Frontend

Frontend work is secondary for this pass. Add only a small operator page if the backend acceptance path is stable:

- Route: `/novel/source-insight`
- Page: `frontend/src/features/novel/SourceInsightWorkbenchPage.tsx`
- API module: `frontend/src/api/modules/sourceInsight.ts`

The page should start a scenario, show the report, and link to existing pages for source rules, AI workspace, and review queue. It should not become a new all-in-one autonomous agent console.

## Handling Current Dirty Workspace

The current checkout contains line-ending-only drift and a large `shareBookSource.json` path/encoding movement. This work must not stage unrelated drift.

Rules:

1. Keep `测试源/shareBookSource.json` available as a local fixture candidate.
2. Do not commit the large fixture movement unless explicitly requested.
3. Do not commit CRLF-only changes in tests or docs.
4. Stage only files created or semantically changed for this acceptance workflow.

## Verification Plan

1. Unit-test the acceptance service with fake source repo, fake fetcher, fake complement, fake knowledge service, and fake provider.
2. Contract-test the smoke script with a tiny fixture source JSON, not the 21.6MB local file.
3. Contract-test the source-build-engine path with fake probe evidence that confirms the report includes job id, source version id, agent run id, decision, rule patch, and generated source rule.
4. Run existing focused backend tests:
   - `tests/test_source_read_service.py`
   - `tests/test_source_complement_app_service.py`
   - `tests/test_character_calibration_service.py`
   - `tests/test_work_knowledge_service.py`
5. Run the smoke script without AI in fixture mode and confirm it produces a deterministic report.
6. Run the smoke script in real-source mode for the four configured URLs and confirm source-build outcomes are recorded for all targets.
7. After provider API credentials are supplied, run the smoke script with `use_ai=true` and confirm only the analysis node consumes provider tokens.

## Open Operational Choice

The implementation should default to deterministic smoke mode. Real network/source testing should be enabled by an explicit flag because it may be slow, flaky, or blocked by source websites.

Recommended defaults:

- `--fixture-mode` for CI and local regression.
- `--real-source-mode` for operator smoke testing.
- `--use-ai` only after credentials are configured.
