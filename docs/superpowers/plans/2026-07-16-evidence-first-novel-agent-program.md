# Evidence-First Novel Agent Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build a resumable, evidence-backed novel analysis system with automated independent adjudication and extensible tabbed System Settings.

**Architecture:** Published healthy sources remain the only ingestion path. Canonical content receives aligned variants, evidence spans anchor claims, and a task runtime drives extraction, verification, adjudication, and targeted re-audit through the existing provider routes. Settings are registry-driven at /system/settings/{domain}/{tab}; Agent policy refers to provider routes and never stores provider credentials.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy/SQLite, React, TypeScript, React Router, Vitest, pytest, pytest-asyncio.

---

## Milestones

1. Settings registry and Agent governance controls.
2. Evidence ingestion and audited source-reading tools.
3. Narrative knowledge, retrieval, and work-analysis UI.
4. Resumable task pipeline, automated adjudication, and real-provider acceptance.

Do not combine milestones in one pull request. Each milestone is independently deployable.

## Milestone 1: Settings registry and governance controls

### Task 1: Add versioned JSON storage for registered setting sections

**Files:**
- Modify: backend/app/domain/repositories/system_settings_repo.py
- Modify: backend/app/infrastructure/persistence/sqlite/system_settings_repo_impl.py
- Create: backend/tests/test_system_settings_repository.py

- [ ] **Step 1: Write failing persistence tests**

~~~python
def test_json_setting_round_trips_with_new_version(repository):
    first = repository.put_json('agents.governance', {'enabled': False}, expected_version=None)
    loaded = repository.get_json('agents.governance', default={'enabled': True})
    second = repository.put_json('agents.governance', {'enabled': True}, expected_version=first.version)

    assert loaded.value == {'enabled': False}
    assert second.value == {'enabled': True}
    assert second.version != first.version


def test_json_setting_rejects_stale_version(repository):
    first = repository.put_json('agents.governance', {'enabled': False}, expected_version=None)
    repository.put_json('agents.governance', {'enabled': True}, expected_version=first.version)

    with pytest.raises(ConcurrentSettingsUpdateError):
        repository.put_json('agents.governance', {'enabled': False}, expected_version=first.version)
~~~

- [ ] **Step 2: Run the test to verify it fails**

Run: PYTHONPATH=backend pytest backend/tests/test_system_settings_repository.py -q

Expected: FAIL because VersionedSetting, get_json, put_json, and ConcurrentSettingsUpdateError are absent.

- [ ] **Step 3: Implement the repository contract**

~~~python
@dataclass(frozen=True)
class VersionedSetting:
    value: dict[str, object]
    version: str
    updated_at: datetime


class ConcurrentSettingsUpdateError(RuntimeError):
    pass


def put_json(self, key: str, value: dict[str, object], expected_version: str | None) -> VersionedSetting:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    row = self._upsert_json_if_version_matches(key, canonical, expected_version)
    return self._to_versioned_setting(row)
~~~

Store canonical JSON. Derive a section version from canonical value and updated_at. Preserve existing bool and int helpers because source-build and browser settings still use them.

- [ ] **Step 4: Run the repository tests**

Run: PYTHONPATH=backend pytest backend/tests/test_system_settings_repository.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/app/domain/repositories/system_settings_repo.py backend/app/infrastructure/persistence/sqlite/system_settings_repo_impl.py backend/tests/test_system_settings_repository.py
git commit -m "feat: add versioned system setting storage"
~~~

### Task 2: Define Agent settings domains, policy normalization, and HTTP APIs

**Files:**
- Create: backend/app/application/services/system_settings_registry.py
- Modify: backend/app/application/services/system_settings_service.py
- Modify: backend/app/interfaces/http/system.py
- Modify: backend/app/application/services/provider_platform_service.py
- Modify: backend/app/infrastructure/persistence/sqlite/bootstrap.py
- Create: backend/tests/test_system_settings_registry.py
- Create: backend/tests/test_api_system_settings_registry.py

- [ ] **Step 1: Write failing policy and HTTP conflict tests**

~~~python
def test_governance_save_clamps_budget_and_returns_canonical_value(service):
    saved = service.save_section(
        'agents', 'governance',
        {'max_tool_calls_per_task': 999, 'max_chapters_per_task': 0},
        expected_version=None,
    )

    assert saved['value']['max_tool_calls_per_task'] == 100
    assert saved['value']['max_chapters_per_task'] == 1


def test_stale_section_save_returns_409(client, admin_headers):
    first = client.get('/api/system/settings/agents/governance', headers=admin_headers).json()['data']
    client.put('/api/system/settings/agents/governance', headers=admin_headers, json={
        'value': {'enabled': False}, 'expected_version': first['version'],
    })
    stale = client.put('/api/system/settings/agents/governance', headers=admin_headers, json={
        'value': {'enabled': True}, 'expected_version': first['version'],
    })

    assert stale.status_code == 409
~~~

- [ ] **Step 2: Run the tests to verify they fail**

Run: PYTHONPATH=backend pytest backend/tests/test_system_settings_registry.py backend/tests/test_api_system_settings_registry.py -q

Expected: FAIL because registry and routes are absent.

- [ ] **Step 3: Implement defaults, normalizer, routes, and role groups**

~~~python
AGENT_GOVERNANCE_DEFAULTS = {
    'enabled': True,
    'background_incremental_enabled': False,
    'automatic_publish_explicit': True,
    'automatic_publish_inferred': False,
    'minimum_inferred_evidence': 2,
    'max_chapters_per_task': 12,
    'max_tool_calls_per_task': 24,
    'max_tokens_per_task': 24000,
    'max_concurrent_tasks': 1,
    'emergency_pause': False,
}


def normalize_governance(value: dict[str, object]) -> dict[str, object]:
    merged = {**AGENT_GOVERNANCE_DEFAULTS, **value}
    merged['max_chapters_per_task'] = min(max(int(merged['max_chapters_per_task']), 1), 50)
    merged['max_tool_calls_per_task'] = min(max(int(merged['max_tool_calls_per_task']), 1), 100)
    merged['max_tokens_per_task'] = min(max(int(merged['max_tokens_per_task']), 1000), 200000)
    merged['minimum_inferred_evidence'] = min(max(int(merged['minimum_inferred_evidence']), 2), 8)
    merged['max_concurrent_tasks'] = min(max(int(merged['max_concurrent_tasks']), 1), 8)
    return merged
~~~

Register domains General, Security and Access, Models and Providers, Agents and Automation, Sources and Browser, Storage and Maintenance, and Runtime and Observability. Register Agent tabs overview, roles, automation, governance, budgets, and audit. Add GET and PUT /api/system/settings/{domain}/{tab}; return normalized value, version, and updated_at; map stale values to HTTP 409.

The roles section persists extractor_route_group, verifier_route_group, adjudicator_route_group, and auditor_route_group, with defaults novel_extract, novel_verify, novel_adjudicate, and novel_audit. Validate every saved value against PROVIDER_ROUTE_GROUPS. The automation section persists enabled, background_incremental_enabled, and emergency_pause. The budgets section owns the bounded integer values from AGENT_GOVERNANCE_DEFAULTS; the governance section owns publication thresholds and escalation rules.

Extend PROVIDER_ROUTE_GROUPS with novel_extract, novel_verify, novel_adjudicate, and novel_audit. Bootstrap routes only from existing configured provider accounts; do not copy credentials.

- [ ] **Step 4: Run API tests**

Run: PYTHONPATH=backend pytest backend/tests/test_system_settings_registry.py backend/tests/test_api_system_settings_registry.py backend/tests/test_api_system_settings.py backend/tests/test_api_provider_platform.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/app/application/services/system_settings_registry.py backend/app/application/services/system_settings_service.py backend/app/interfaces/http/system.py backend/app/application/services/provider_platform_service.py backend/app/infrastructure/persistence/sqlite/bootstrap.py backend/tests/test_system_settings_registry.py backend/tests/test_api_system_settings_registry.py
git commit -m "feat: add agent governance settings API"
~~~

### Task 3: Build the registry-driven System Settings shell

**Files:**
- Create: frontend/src/features/system/settingsRegistry.ts
- Create: frontend/src/features/system/SystemSettingsLayout.tsx
- Create: frontend/src/features/system/AgentGovernanceSettings.tsx
- Create: frontend/src/features/system/AgentRoleSettings.tsx
- Create: frontend/src/features/system/AgentAutomationSettings.tsx
- Create: frontend/src/features/system/AgentBudgetSettings.tsx
- Create: frontend/src/features/system/AgentAuditSettings.tsx
- Modify: frontend/src/features/system/SystemSettingsPage.tsx
- Modify: frontend/src/api/modules/system.ts
- Modify: frontend/src/app/router.tsx
- Create: frontend/src/features/system/SystemSettingsLayout.test.tsx
- Create: frontend/src/features/system/AgentGovernanceSettings.test.tsx

- [ ] **Step 1: Write failing deep-link and canonical-save tests**

~~~tsx
test('deep link selects the requested Agent governance tab', async () => {
  renderAt('/system/settings/agents/governance')
  expect(await screen.findByRole('tab', { name: 'Evidence and governance' })).toHaveAttribute('aria-selected', 'true')
})


test('governance save replaces local edits with server canonical value', async () => {
  saveSettingsSection.mockResolvedValue(envelope({
    value: { enabled: true, max_tool_calls_per_task: 100 },
    version: 'v2',
    updated_at: '2026-07-16T00:00:00Z',
  }))
  render(<AgentGovernanceSettings />)
  await userEvent.click(screen.getByRole('button', { name: 'Save governance settings' }))

  expect(await screen.findByText(/Effective/)).toBeInTheDocument()
  expect(screen.getByDisplayValue('100')).toBeInTheDocument()
})
~~~

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run: npm --prefix frontend test -- --run src/features/system/SystemSettingsLayout.test.tsx src/features/system/AgentGovernanceSettings.test.tsx

Expected: FAIL because layout and section client are absent.

- [ ] **Step 3: Implement route-aware navigation**

~~~ts
export const SETTINGS_DOMAINS = [{
  id: 'agents',
  label: 'Agents and automation',
  tabs: [
    { id: 'overview', label: 'Overview' },
    { id: 'roles', label: 'Roles and models' },
    { id: 'automation', label: 'Automation' },
    { id: 'governance', label: 'Evidence and governance' },
    { id: 'budgets', label: 'Budgets and queue' },
    { id: 'audit', label: 'Audit and tests' },
  ],
}]
~~~

Redirect /system/settings to /system/settings/models/providers. Preserve ProviderRoutingSettings inside models/providers. Use a left domain navigation plus an accessible tablist. On narrow screens replace the tablist with a labeled select that navigates to the same URL. Show a conflict banner for HTTP 409 and preserve unsaved edits until reload.

Render AgentRoleSettings for roles, AgentAutomationSettings for automation, AgentGovernanceSettings for governance, AgentBudgetSettings for budgets, and AgentAuditSettings for audit. Each component loads and saves only its own registered section, replaces its local state with the canonical save response, and displays the server effective time. AgentAuditSettings provides the dry-run trigger, decision-log link, and emergency-pause control; it does not display provider credentials.

- [ ] **Step 4: Run tests and build**

Run: npm --prefix frontend test -- --run src/features/system/SystemSettingsPage.test.tsx src/features/system/SystemSettingsLayout.test.tsx src/features/system/AgentGovernanceSettings.test.tsx

Expected: PASS.

Run: npm --prefix frontend run build

Expected: exit 0.

- [ ] **Step 5: Commit**

~~~bash
git add frontend/src/features/system frontend/src/api/modules/system.ts frontend/src/app/router.tsx
git commit -m "feat: add tabbed system settings architecture"
~~~

## Milestone 2: Evidence ingestion and audited reading

### Task 4: Persist immutable evidence spans

**Files:**
- Modify: backend/app/infrastructure/persistence/sqlite/schema.py
- Create: backend/app/domain/entities/evidence.py
- Create: backend/app/infrastructure/persistence/sqlite/evidence_repo_impl.py
- Create: backend/app/application/services/evidence_service.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Create: backend/tests/test_evidence_service.py

- [ ] **Step 1: Write failing evidence tests**

~~~python
def test_span_creation_is_hashed_and_non_overlapping(service):
    spans = service.create_spans(
        content_variant_id='variant-1',
        canonical_chapter_id='chapter-1',
        content='甲。乙。丙。',
        max_chars=3,
    )

    assert [span.excerpt for span in spans] == ['甲。', '乙。', '丙。']
    assert all(span.content_sha256 for span in spans)
    assert spans[0].end_offset <= spans[1].start_offset


def test_verified_span_is_unavailable_when_variant_content_changes(service):
    span = service.create_spans(
        content_variant_id='variant-1',
        canonical_chapter_id='chapter-1',
        content='证据正文',
        max_chars=100,
    )[0]
    service.set_content_for_test('variant-1', '已变化正文')

    assert service.get_verified_span(span.id) is None
~~~

- [ ] **Step 2: Run the evidence test to verify it fails**

Run: PYTHONPATH=backend pytest backend/tests/test_evidence_service.py -q

Expected: FAIL because models and service are absent.

- [ ] **Step 3: Implement immutable spans**

~~~python
@dataclass(frozen=True)
class EvidenceSpan:
    id: str
    canonical_chapter_id: str
    content_variant_id: str
    start_offset: int
    end_offset: int
    excerpt: str
    excerpt_sha256: str
    content_sha256: str
    created_at: datetime | None = None
~~~

Create evidence_spans with indexes on canonical_chapter_id, content_variant_id, and content_sha256. Split normalized content at sentence boundaries when possible and never split a Unicode code point. Hash UTF-8 content and excerpts with SHA-256. Recompute the variant hash before returning a verified span.

- [ ] **Step 4: Run evidence tests**

Run: PYTHONPATH=backend pytest backend/tests/test_evidence_service.py backend/tests/test_canonical_content_service.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/app/infrastructure/persistence/sqlite/schema.py backend/app/domain/entities/evidence.py backend/app/infrastructure/persistence/sqlite/evidence_repo_impl.py backend/app/application/services/evidence_service.py backend/app/infrastructure/persistence/factory.py backend/tests/test_evidence_service.py
git commit -m "feat: persist immutable chapter evidence spans"
~~~

### Task 5: Ingest selected chapters and bind audited Agent reading tools

**Files:**
- Create: backend/app/application/services/work_ingestion_service.py
- Create: backend/app/application/services/novel_analysis_tool_executor.py
- Modify: backend/app/application/services/agent_tool_registry.py
- Modify: backend/app/application/services/agent_runtime_service.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Create: backend/tests/test_work_ingestion_service.py
- Create: backend/tests/test_novel_analysis_tool_executor.py

- [ ] **Step 1: Write failing source-to-evidence and tool-audit tests**

~~~python
@pytest.mark.asyncio
async def test_selected_source_chapter_becomes_canonical_evidence(ingestion_service):
    result = await ingestion_service.fetch_and_ingest_chapter(
        source_id=7,
        book_url='https://source.test/book/1',
        chapter_index=0,
        book_name='测试书',
        author_hint='作者',
    )

    assert result.canonical_work_id
    assert result.content_variant_id
    assert result.evidence_span_ids


@pytest.mark.asyncio
async def test_chapter_fetch_tool_records_evidence_and_limits_preview(executor):
    result = await executor.ainvoke('chapter.fetch', {
        'tenant_id': 'tenant-1',
        'source_id': 7,
        'book_url': 'https://source.test/book/1',
        'chapter_index': 0,
        'book_name': '测试书',
    })

    assert result.status == 'accepted'
    assert result.data['evidence_span_ids']
    assert len(result.data['content_preview']) <= 1200
~~~

- [ ] **Step 2: Run the tests to verify they fail**

Run: PYTHONPATH=backend pytest backend/tests/test_work_ingestion_service.py backend/tests/test_novel_analysis_tool_executor.py -q

Expected: FAIL because facade and handlers are absent.

- [ ] **Step 3: Implement bounded ingestion and tools**

~~~python
async def fetch_and_ingest_chapter(
    self,
    *,
    source_id: int,
    book_url: str,
    chapter_index: int,
    book_name: str,
    author_hint: str | None,
) -> IngestedChapter:
    source = await self._require_healthy_published_source(source_id)
    toc = await self._reader.get_book_toc(source_id, book_url, book_name, author_hint)
    chapter = toc['chapters'][chapter_index]
    content = await self._reader.get_chapter_content(
        source_id, chapter['url'], book_name, author_hint, chapter['title'], chapter_index,
    )
    return await self._persist(source, book_name, author_hint, chapter, content)
~~~

Bind source.search, book.resolve, toc.get, chapter.fetch, evidence.search, and evidence.get only for knowledge Agent handlers. Reject arbitrary URLs, disabled or non-published sources, cross-tenant IDs, and chapter indexes outside the returned table of contents. Record ToolInvocation, ToolResult, and one ToolEvidence row for every returned span.

- [ ] **Step 4: Run source and authorization tests**

Run: PYTHONPATH=backend pytest backend/tests/test_work_ingestion_service.py backend/tests/test_novel_analysis_tool_executor.py backend/tests/test_agent_tool_registry.py backend/tests/test_agent_runtime_service.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/app/application/services/work_ingestion_service.py backend/app/application/services/novel_analysis_tool_executor.py backend/app/application/services/agent_tool_registry.py backend/app/application/services/agent_runtime_service.py backend/app/infrastructure/persistence/factory.py backend/tests/test_work_ingestion_service.py backend/tests/test_novel_analysis_tool_executor.py
git commit -m "feat: add audited source-to-evidence tools"
~~~

## Milestone 3: Narrative knowledge and work retrieval

### Task 6: Add claims, events, chronology, and conflicts

**Files:**
- Modify: backend/app/infrastructure/persistence/sqlite/schema.py
- Create: backend/app/domain/entities/narrative_knowledge.py
- Create: backend/app/infrastructure/persistence/sqlite/narrative_knowledge_repo_impl.py
- Create: backend/app/application/services/narrative_knowledge_service.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Create: backend/tests/test_narrative_knowledge_service.py

- [ ] **Step 1: Write failing lifecycle tests**

~~~python
def test_conflict_does_not_overwrite_published_claim(service, evidence_ids):
    published = service.create_claim('work-1', 'entity-a', 'alive', scalar_value=True, epistemic='explicit', evidence_ids=evidence_ids)
    service.publish_claim(published.id, actor_id='adjudicator')
    candidate = service.create_claim('work-1', 'entity-a', 'alive', scalar_value=False, epistemic='explicit', evidence_ids=evidence_ids)

    conflict = service.detect_conflicts(candidate.id)

    assert conflict.status == 'open'
    assert service.get_claim(published.id).status == 'published'
    assert service.get_claim(candidate.id).status == 'candidate'


def test_inferred_claim_with_one_span_is_not_publishable(service):
    claim = service.create_claim(
        'work-1', 'entity-a', 'trusts',
        object_entity_id='entity-b',
        epistemic='inferred',
        evidence_ids=['span-1'],
    )

    assert service.publishability(claim.id).allowed is False
~~~

- [ ] **Step 2: Run the tests to verify they fail**

Run: PYTHONPATH=backend pytest backend/tests/test_narrative_knowledge_service.py -q

Expected: FAIL because narrative claim storage is absent.

- [ ] **Step 3: Implement relational narrative knowledge**

~~~python
@dataclass(frozen=True)
class KnowledgeClaim:
    id: str
    work_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str | None
    scalar_value: dict[str, object] | None
    epistemic: Literal['explicit', 'inferred', 'speculative']
    status: Literal['candidate', 'published', 'superseded', 'withdrawn']
~~~

Create models and repositories for knowledge_entities, knowledge_entity_aliases, knowledge_claims, claim_evidence, narrative_events, event_participants, temporal_links, and knowledge_conflicts. Require verified evidence before adjudication. Add work/status and subject/predicate indexes. Do not auto-merge aliases.

- [ ] **Step 4: Run knowledge tests**

Run: PYTHONPATH=backend pytest backend/tests/test_narrative_knowledge_service.py backend/tests/test_work_knowledge_service.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/app/infrastructure/persistence/sqlite/schema.py backend/app/domain/entities/narrative_knowledge.py backend/app/infrastructure/persistence/sqlite/narrative_knowledge_repo_impl.py backend/app/application/services/narrative_knowledge_service.py backend/app/infrastructure/persistence/factory.py backend/tests/test_narrative_knowledge_service.py
git commit -m "feat: add evidence-backed narrative knowledge"
~~~

### Task 7: Add bounded work snapshot and evidence APIs

**Files:**
- Create: backend/app/interfaces/http/novel_analysis.py
- Modify: backend/app/interfaces/http/router.py
- Create: backend/tests/test_api_novel_analysis.py

- [ ] **Step 1: Write failing API tests**

~~~python
def test_snapshot_returns_published_claims_and_open_conflicts(client, headers):
    response = client.get('/api/novel-analysis/works/work-1/snapshot?chapter_limit=8', headers=headers)

    assert response.status_code == 200
    assert 'published_claims' in response.json()['data']
    assert 'open_conflicts' in response.json()['data']


def test_evidence_read_returns_excerpt_and_provenance(client, headers):
    response = client.get('/api/novel-analysis/evidence/span-1', headers=headers)

    assert response.status_code == 200
    assert response.json()['data']['excerpt']
    assert response.json()['data']['content_sha256']
~~~

- [ ] **Step 2: Run the tests to verify they fail**

Run: PYTHONPATH=backend pytest backend/tests/test_api_novel_analysis.py -q

Expected: FAIL with route-not-found responses.

- [ ] **Step 3: Implement read endpoints**

~~~python
@router.get('/works/{work_id}/snapshot')
async def get_work_snapshot(
    work_id: str,
    chapter_limit: int = Query(default=8, ge=1, le=24),
    identity: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    return envelope(build_narrative_knowledge_service().build_work_snapshot(work_id, chapter_limit=chapter_limit))


@router.get('/evidence/{evidence_id}')
async def get_evidence(
    evidence_id: str,
    identity: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    return envelope(build_evidence_service().get_verified_evidence_or_raise(evidence_id))
~~~

Return source name, canonical chapter title, offsets, excerpt, hashes, and creation time. Do not expose source headers, complete content variants, or provider data.

- [ ] **Step 4: Run API tests**

Run: PYTHONPATH=backend pytest backend/tests/test_api_novel_analysis.py backend/tests/test_api_work_knowledge.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/app/interfaces/http/novel_analysis.py backend/app/interfaces/http/router.py backend/tests/test_api_novel_analysis.py
git commit -m "feat: expose evidence-backed work retrieval"
~~~

## Milestone 4: Resumable analysis, adjudication, and acceptance

### Task 8: Implement analysis tasks, checkpoints, and independent Agent roles

**Files:**
- Modify: backend/app/infrastructure/persistence/sqlite/schema.py
- Create: backend/app/domain/entities/novel_analysis_task.py
- Create: backend/app/infrastructure/persistence/sqlite/novel_analysis_task_repo_impl.py
- Create: backend/app/application/services/novel_analysis_task_service.py
- Create: backend/app/application/services/novel_analysis_prompts.py
- Create: backend/app/application/services/novel_analysis_pipeline_service.py
- Modify: backend/app/infrastructure/persistence/factory.py
- Create: backend/tests/test_novel_analysis_task_service.py
- Create: backend/tests/test_novel_analysis_pipeline_service.py

- [ ] **Step 1: Write failing task and adjudication tests**

~~~python
def test_task_pauses_at_tool_budget_and_resumes_from_checkpoint(service):
    task = service.create_task('work-1', 'tenant-1', '分析主角关系', {'max_tool_calls_per_task': 2})
    service.record_tool_progress(task.id, ['span-1'])
    service.record_tool_progress(task.id, ['span-2'])

    paused = service.get_task(task.id)
    resumed = service.resume(task.id, tenant_id='tenant-1')

    assert paused.status == 'paused'
    assert paused.checkpoint['selected_evidence_ids'] == ['span-1', 'span-2']
    assert resumed.status == 'queued'


@pytest.mark.asyncio
async def test_identity_merge_escalates_even_when_models_agree(pipeline, identity_merge_claim):
    outcome = await pipeline.process_claim(identity_merge_claim.id, tenant_id='tenant-1')

    assert outcome.verdict == 'human_review'
    assert outcome.claim_status == 'candidate'
~~~

- [ ] **Step 2: Run the tests to verify they fail**

Run: PYTHONPATH=backend pytest backend/tests/test_novel_analysis_task_service.py backend/tests/test_novel_analysis_pipeline_service.py -q

Expected: FAIL because task and pipeline services are absent.

- [ ] **Step 3: Implement task and role isolation**

~~~python
ROLE_GROUPS = {
    'extractor': 'novel_extract',
    'verifier': 'novel_verify',
    'adjudicator': 'novel_adjudicate',
    'auditor': 'novel_audit',
}


async def process_claim(self, claim_id: str, tenant_id: str) -> AdjudicationOutcome:
    verified = await self._verify_claim_from_evidence(claim_id, tenant_id)
    decision = await self._adjudicate_from_evidence(claim_id, verified.evidence_ids, tenant_id)
    return self._apply_policy_and_record(claim_id, verified, decision)
~~~

Persist agent_analysis_tasks, agent_task_checkpoints, and knowledge_adjudications. Check emergency_pause and every budget before new tool calls. Verifier and adjudicator load evidence independently. Deterministically escalate speculative claims, identity merges, retcons, and direct conflicts before a model verdict can publish them.

- [ ] **Step 4: Run task and pipeline tests**

Run: PYTHONPATH=backend pytest backend/tests/test_novel_analysis_task_service.py backend/tests/test_novel_analysis_pipeline_service.py backend/tests/test_provider_platform_service.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add backend/app/infrastructure/persistence/sqlite/schema.py backend/app/domain/entities/novel_analysis_task.py backend/app/infrastructure/persistence/sqlite/novel_analysis_task_repo_impl.py backend/app/application/services/novel_analysis_task_service.py backend/app/application/services/novel_analysis_prompts.py backend/app/application/services/novel_analysis_pipeline_service.py backend/tests/test_novel_analysis_task_service.py backend/tests/test_novel_analysis_pipeline_service.py
git commit -m "feat: add resumable novel analysis adjudication"
~~~

### Task 9: Add task controls, targeted re-audit, and evidence-first work UI

**Files:**
- Modify: backend/app/interfaces/http/novel_analysis.py
- Modify: backend/app/tasks/scheduler.py
- Create: backend/tests/test_api_novel_analysis_tasks.py
- Create: backend/tests/test_novel_analysis_regression_audit.py
- Create: frontend/src/api/modules/novelAnalysis.ts
- Create: frontend/src/features/novel-analysis/WorkAnalysisPage.tsx
- Create: frontend/src/features/novel-analysis/EvidenceDrawer.tsx
- Create: frontend/src/features/novel-analysis/TaskStatusCard.tsx
- Modify: frontend/src/app/router.tsx
- Create: frontend/src/features/novel-analysis/WorkAnalysisPage.test.tsx

- [ ] **Step 1: Write failing control, re-audit, and citation UI tests**

~~~python
def test_pause_preserves_checkpoint_and_blocks_new_lease(client, headers):
    task_id = create_task(client, headers)
    paused = client.post(f'/api/novel-analysis/tasks/{task_id}/pause', headers=headers)

    assert paused.status_code == 200
    assert paused.json()['data']['status'] == 'paused'


@pytest.mark.asyncio
async def test_variant_change_reaudits_only_linked_claims(audit_service):
    result = await audit_service.reaudit_content_variant('variant-1')

    assert result.reaudited_claim_ids == ['claim-linked']
~~~

~~~tsx
test('published claim opens exact evidence citation', async () => {
  getWorkSnapshot.mockResolvedValue(envelope(snapshotFixture))
  getEvidence.mockResolvedValue(envelope(evidenceFixture))
  renderAt('/novel-analysis/work-1')

  await userEvent.click(await screen.findByRole('button', { name: /宁姚/ }))
  expect(await screen.findByText('Evidence excerpt')).toBeInTheDocument()
  expect(screen.getByText('Chapter 12')).toBeInTheDocument()
})
~~~

- [ ] **Step 2: Run the tests to verify they fail**

Run: PYTHONPATH=backend pytest backend/tests/test_api_novel_analysis_tasks.py backend/tests/test_novel_analysis_regression_audit.py -q

Expected: FAIL because controls and audit are absent.

Run: npm --prefix frontend test -- --run src/features/novel-analysis/WorkAnalysisPage.test.tsx

Expected: FAIL because analysis route is absent.

- [ ] **Step 3: Implement controls, audit, and UI**

~~~python
@router.post('/tasks/{task_id}/pause')
async def pause_task(
    task_id: str,
    identity: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    return envelope(build_novel_analysis_task_service().pause(task_id, tenant_id=str(identity.user_id)))


@router.post('/tasks/{task_id}/resume')
async def resume_task(
    task_id: str,
    identity: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    return envelope(build_novel_analysis_task_service().resume(task_id, tenant_id=str(identity.user_id)))
~~~

The scheduler leases queued tasks only when background_incremental_enabled is true and emergency_pause is false. Re-audit by joining claim_evidence to spans belonging to the changed variant; do not scan every work claim. The UI separates published claims, candidates, and conflicts; every claim opens EvidenceDrawer and each task shows remaining budget, checkpoint time, pause/resume, and adjudication reason.

- [ ] **Step 4: Run focused verification**

Run: PYTHONPATH=backend pytest backend/tests/test_api_novel_analysis_tasks.py backend/tests/test_novel_analysis_regression_audit.py backend/tests/test_novel_analysis_task_service.py backend/tests/test_novel_analysis_pipeline_service.py -q

Expected: PASS.

Run: npm --prefix frontend test -- --run src/features/novel-analysis/WorkAnalysisPage.test.tsx src/features/system/AgentGovernanceSettings.test.tsx

Expected: PASS.

Run: npm --prefix frontend run build

Expected: exit 0.

- [ ] **Step 5: Commit**

~~~bash
git add backend/app/interfaces/http/novel_analysis.py backend/app/tasks/scheduler.py backend/tests/test_api_novel_analysis_tasks.py backend/tests/test_novel_analysis_regression_audit.py frontend/src/api/modules/novelAnalysis.ts frontend/src/features/novel-analysis frontend/src/app/router.tsx
git commit -m "feat: add novel analysis controls and evidence UI"
~~~

### Task 10: Add opt-in real-provider acceptance after credentials are supplied

**Files:**
- Create: backend/tests/test_real_evidence_first_novel_agent.py
- Modify: docs/superpowers/specs/2026-07-16-evidence-first-novel-agent-design.md

- [ ] **Step 1: Write the opt-in real-provider test**

~~~python
pytestmark = pytest.mark.skipif(
    os.getenv('RUN_REAL_PROVIDER_TESTS') != '1',
    reason='requires user-configured provider credentials and approved healthy source',
)


@pytest.mark.asyncio
async def test_real_source_to_evidence_to_adjudicated_claim(real_stack):
    chapter = await real_stack.ingest_from_source(
        keyword='剑来',
        source_id=real_stack.source_id,
        chapter_index=0,
    )
    task = real_stack.create_task(chapter.canonical_work_id, '识别本章人物与事件')
    outcome = await real_stack.run_task(task.id)

    assert chapter.evidence_span_ids
    assert outcome.adjudications
    assert all(item.evidence_ids for item in outcome.adjudications)
~~~

- [ ] **Step 2: Verify it is skipped without credentials**

Run: PYTHONPATH=backend pytest backend/tests/test_real_evidence_first_novel_agent.py -q

Expected: 1 skipped.

- [ ] **Step 3: Add environment gating and redaction**

Read source ID and provider route groups only from test-only environment variables. Never print API keys, source headers, raw full chapter text, or model request bodies. Assert evidence IDs, task checkpoints, and verdicts rather than model prose.

- [ ] **Step 4: Run real acceptance after the user supplies credentials**

Run: RUN_REAL_PROVIDER_TESTS=1 PYTHONPATH=backend pytest backend/tests/test_real_evidence_first_novel_agent.py -q

Expected: PASS against a user-approved healthy published source.

- [ ] **Step 5: Run full focused regression and commit**

Run: PYTHONPATH=backend pytest backend/tests/test_system_settings_repository.py backend/tests/test_system_settings_registry.py backend/tests/test_api_system_settings_registry.py backend/tests/test_evidence_service.py backend/tests/test_work_ingestion_service.py backend/tests/test_narrative_knowledge_service.py backend/tests/test_novel_analysis_task_service.py backend/tests/test_novel_analysis_pipeline_service.py backend/tests/test_api_novel_analysis.py backend/tests/test_api_novel_analysis_tasks.py -q

Expected: PASS.

Run: npm --prefix frontend test -- --run src/features/system src/features/novel-analysis

Expected: PASS.

Run: npm --prefix frontend run build

Expected: exit 0.

~~~bash
git add backend/tests/test_real_evidence_first_novel_agent.py docs/superpowers/specs/2026-07-16-evidence-first-novel-agent-design.md
git commit -m "test: add real novel agent acceptance"
~~~

## Program-level verification checklist

- [ ] Bootstrap creates new tables and indexes without changing existing source, provider, canonical-content, or work-knowledge rows.
- [ ] /system/settings redirects to /system/settings/models/providers; every registered tab has a stable direct URL.
- [ ] A stale settings save returns HTTP 409 and client edits remain available until resolved.
- [ ] A healthy published source creates canonical content, a content variant, and verified evidence spans.
- [ ] Every displayed knowledge conclusion cites verified evidence; stale evidence cannot publish.
- [ ] Budget exhaustion stores a checkpoint; resume uses stored evidence rather than refetching it.
- [ ] Explicit safe facts can auto-publish; inferred, speculative, identity, and conflict cases follow policy gates.
- [ ] Emergency pause prevents new task leases and pauses running work at the next checkpoint.
