# Provider Platform for AI, Translation, and Novel Design

> Date: 2026-07-07  
> Workspace: `C:\Users\lihuo\Desktop\legado-hub`  
> Subproject: 4 / 4  
> Runtime target: local Python 3.13 backend with real external providers and local SQLite state  
> Git note: this workspace currently has no `.git`; write files directly and use filesystem checkpoints instead of commits.

---

## 1. Goal

Turn the current AI / translation / novel shells into a real provider-driven platform. All three domains must execute real tasks against real providers, record usage/cost/failure data, expose operational controls through the main API, and integrate into the unified control plane.

## 2. Confirmed decisions

- Real providers are required in the first milestone; no stub-only phase.
- Provider plumbing is shared across AI, translation, and novel.
- Credentials, models, quotas, usage, retry/fallback, and health all need first-class operational support.
- The UI for these domains lives inside the super admin console rather than a separate frontend.

## 3. Scope

### In scope

- Provider registry, credential storage metadata, model catalog, health checks
- Shared task dispatcher with retries, fallback, cancellation, usage/cost metering, quota enforcement
- AI domain task types for structured generation/analysis
- Translation domain chunked task flow with dictionary support
- Novel ingestion + processing + result flow
- Authenticated APIs and control-plane views for all above

### Out of scope

- Building a distributed queue farm in the first release
- Supporting every possible provider protocol at once
- Replacing the new main API with domain-specific standalone services

## 4. Platform architecture

The provider platform is split into a shared layer and domain layers.

### Shared layer

- `ProviderRegistry`
- `CredentialStore` metadata
- `ModelCatalog`
- `TaskDispatcher`
- `RetryPolicy`
- `FallbackPolicy`
- `UsageMetering`
- `QuotaLimiter`
- `AuditRecorder`

### Domain layers

- AI domain
- Translation domain
- Novel domain

The shared layer normalizes provider calls and operational concerns. Each domain keeps its own orchestration and result schema.

## 5. Shared runtime requirements

- Provider instances can be enabled/disabled and validated
- Credentials are masked in responses
- Each task stores provider, model, attempt count, latency, token/character usage, cost, and failure reason
- Quotas can be enforced per user, role, or API key
- Retry and fallback policies are explicit and observable
- Provider health is queryable by the console

## 6. Domain requirements

### AI

First release focuses on structured analysis/generation tasks such as character analysis, world analysis, storyline analysis, and structured summaries. Results must be versioned by provider/model/prompt template.

### Translation

Translation tasks support large text chunking, dictionary/terminology inputs, per-chunk retries, provider fallback, result merge, and progress tracking.

### Novel

Novel processing is modeled as ingestion -> processing -> results. Ingestion stores source text/chapters; processing can call AI and translation capabilities; result objects remain queryable and auditable.

## 7. API surface

The platform extends the authenticated API with families such as:

- `/api/ai/tasks`
- `/api/ai/providers`
- `/api/ai/models`
- `/api/translation/tasks`
- `/api/translation/providers`
- `/api/translation/dictionaries`
- `/api/novel/tasks`
- `/api/novel/ingestions`
- `/api/novel/results`
- `/api/system/providers`
- `/api/system/quotas`
- `/api/system/usage`

These APIs must use the same auth, RBAC, audit, and response envelope as the rest of the backend.

## 8. Persistence model

SQLite additions should include, at minimum:

- `provider_accounts`
- `provider_models`
- `provider_health_checks`
- `provider_usage_events`
- `quota_policies`
- `quota_usage`
- `ai_tasks` / `ai_results`
- `translation_tasks` / `translation_chunks` / `translation_dictionaries`
- `novel_ingestions` / `novel_tasks` / `novel_results`

## 9. Testing strategy

- Repository tests for provider, quota, and task persistence
- Service tests for retry, fallback, quota enforcement, and cost metering
- API tests for provider CRUD, task creation, status transitions, and result retrieval
- Local smoke scripts for real credential validation and at least one real task per domain when credentials are configured

## 10. Risks and constraints

- Real providers can fail, rate limit, or drift unexpectedly; retries and fallbacks are required before convenience features.
- Costs can grow silently without metering and quotas.
- Novel workflows can sprawl; they must reuse the shared platform instead of building a parallel execution model.
- The project remains local-first with SQLite, so schemas and write patterns must stay lightweight.

## 11. Acceptance criteria

This subproject is complete when:

- AI, translation, and novel all execute real provider-backed tasks
- Provider, model, credential, quota, and usage state are visible through authenticated APIs
- Retry, fallback, cancellation, and cost tracking are implemented and testable
- The super admin console can manage providers and inspect task results/failures
- Local Python 3.13 + SQLite runtime stays operational while using real provider credentials
