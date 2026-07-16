from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_identity_merge_escalates_even_when_models_agree():
    from app.application.services.novel_analysis_pipeline_service import NovelAnalysisPipelineService

    claim = SimpleNamespace(
        id="claim-1",
        predicate="same_identity_as",
        epistemic="explicit",
        evidence_ids=["span-1", "span-2"],
    )

    class Knowledge:
        def get_claim(self, claim_id):
            return claim if claim_id == "claim-1" else None

    pipeline = NovelAnalysisPipelineService(knowledge_service=Knowledge())
    outcome = await pipeline.process_claim("claim-1", tenant_id="tenant-1")

    assert outcome.verdict == "human_review"
    assert outcome.claim_status == "candidate"


@pytest.mark.asyncio
async def test_task_uses_independent_configured_routes_with_only_cited_evidence():
    from app.application.services.novel_analysis_pipeline_service import NovelAnalysisPipelineService
    from app.domain.entities.novel_analysis_task import NovelAnalysisTask

    claim = SimpleNamespace(
        id="claim-1",
        work_id="work-1",
        subject_entity_id="宁姚",
        predicate="protects",
        object_entity_id="陈平安",
        scalar_value=None,
        epistemic="explicit",
        evidence_ids=["span-1"],
    )

    class Knowledge:
        def __init__(self):
            self.published_claim_ids = []

        def build_work_snapshot(self, work_id, *, chapter_limit):
            assert work_id == "work-1"
            assert chapter_limit == 8
            return {"work_id": work_id, "published_claims": [], "open_conflicts": []}

        def create_claim(self, **kwargs):
            assert kwargs["evidence_ids"] == ["span-1"]
            return claim

        def get_claim(self, claim_id):
            return claim if claim_id == "claim-1" else None

        def publishability(self, claim_id):
            assert claim_id == "claim-1"
            return SimpleNamespace(allowed=True, reasons=())

        def detect_conflicts(self, claim_id):
            assert claim_id == "claim-1"
            return None

        def publish_claim(self, claim_id, *, actor_id):
            assert actor_id == "novel-adjudicator"
            self.published_claim_ids.append(claim_id)
            return claim

    class Evidence:
        def get_verified_span(self, evidence_id):
            assert evidence_id == "span-1"
            return SimpleNamespace(
                id="span-1",
                canonical_chapter_id="chapter-12",
                start_offset=12,
                end_offset=24,
                excerpt="宁姚在雨中救下少年。",
                excerpt_sha256="excerpt-hash",
                content_sha256="content-hash",
            )

    class Platform:
        def __init__(self):
            self.calls = []

        async def invoke_chat(self, **kwargs):
            self.calls.append(kwargs)
            outputs = {
                "extract-route": '{"claims":[{"subject_entity_id":"宁姚","predicate":"protects","object_entity_id":"陈平安","epistemic":"explicit","evidence_ids":["span-1"]}]}',
                "verify-route": '{"verdict":"pass","reason":"directly supported"}',
                "adjudicate-route": '{"verdict":"publish","reason":"safe explicit fact"}',
            }
            return {
                "provider_name": "test-provider",
                "model": "test-model",
                "output": {"text": outputs[kwargs["provider_group"]]},
                "usage": {"total_tokens": 12},
            }

    class Settings:
        def get_section(self, domain, tab):
            values = {
                "roles": {
                    "extractor_route_group": "extract-route",
                    "verifier_route_group": "verify-route",
                    "adjudicator_route_group": "adjudicate-route",
                    "auditor_route_group": "audit-route",
                },
                "governance": {
                    "automatic_publish_explicit": True,
                    "automatic_publish_inferred": False,
                    "minimum_inferred_evidence": 2,
                },
            }
            return {"value": values.get(tab, {})}

    class Decisions:
        def __init__(self):
            self.items = []

        def record_adjudication(self, **item):
            self.items.append(item)

    knowledge = Knowledge()
    platform = Platform()
    decisions = Decisions()
    pipeline = NovelAnalysisPipelineService(
        knowledge_service=knowledge,
        evidence_service=Evidence(),
        platform=platform,
        settings_service=Settings(),
        decision_recorder=decisions,
    )
    task = NovelAnalysisTask(
        id="task-1",
        work_id="work-1",
        tenant_id="tenant-1",
        goal="识别这一段中的人物关系",
        policy={"max_tokens_per_task": 1000},
        checkpoint={"selected_evidence_ids": ["span-1"]},
    )

    result = await pipeline.process_task(task, tenant_id="tenant-1")

    assert result.claim_ids == ("claim-1",)
    assert result.outcomes[0].claim_status == "published"
    assert knowledge.published_claim_ids == ["claim-1"]
    assert [call["provider_group"] for call in platform.calls] == [
        "extract-route", "verify-route", "adjudicate-route",
    ]
    assert len(decisions.items) == 2
    assert {item["task_id"] for item in decisions.items} == {"task-1"}
    assert all(item["prompt_version"] == "evidence-first-v1" for item in decisions.items)
    assert all(item["policy"]["max_tokens_per_task"] == 1000 for item in decisions.items)
    prompt_text = "\n".join(
        str(message["content"])
        for call in platform.calls
        for message in call["payload"]["messages"]
        if isinstance(message.get("content"), str)
    )
    assert "宁姚在雨中救下少年。" in prompt_text
    assert "content-hash" in prompt_text
    assert "完整章节正文" not in prompt_text


@pytest.mark.asyncio
async def test_reaudit_task_calls_auditor_before_reverification_and_adjudication():
    from app.application.services.novel_analysis_pipeline_service import NovelAnalysisPipelineService
    from app.domain.entities.novel_analysis_task import NovelAnalysisTask

    claim = SimpleNamespace(
        id="claim-1", work_id="work-1", subject_entity_id="宁姚", predicate="protects",
        object_entity_id="陈平安", scalar_value=None, epistemic="explicit", evidence_ids=["span-1"],
    )

    class Knowledge:
        def get_claim(self, claim_id): return claim if claim_id == claim.id else None
        def publishability(self, _claim_id): return SimpleNamespace(allowed=True, reasons=())
        def detect_conflicts(self, _claim_id): return None
        def publish_claim(self, claim_id, *, actor_id):
            assert (claim_id, actor_id) == ("claim-1", "novel-adjudicator")
            return claim

    class Evidence:
        def get_verified_span(self, evidence_id):
            assert evidence_id == "span-1"
            return SimpleNamespace(
                id="span-1", canonical_chapter_id="chapter-12", start_offset=1, end_offset=8,
                excerpt="宁姚救下少年。", excerpt_sha256="excerpt-hash", content_sha256="content-hash",
            )

    class Platform:
        def __init__(self): self.groups = []
        async def invoke_chat(self, **kwargs):
            self.groups.append(kwargs["provider_group"])
            outputs = {
                "audit-route": '{"verdict":"reaffirm","reason":"evidence remains aligned"}',
                "verify-route": '{"verdict":"pass","reason":"direct support"}',
                "adjudicate-route": '{"verdict":"publish","reason":"safe"}',
            }
            return {"provider_group": kwargs["provider_group"], "provider_name": "test", "model": "test-model", "output": {"text": outputs[kwargs["provider_group"]]}, "usage": {"total_tokens": 3}}

    class Settings:
        def get_section(self, _domain, tab):
            values = {
                "roles": {"extractor_route_group": "extract-route", "verifier_route_group": "verify-route", "adjudicator_route_group": "adjudicate-route", "auditor_route_group": "audit-route"},
                "governance": {"automatic_publish_explicit": True, "automatic_publish_inferred": False, "minimum_inferred_evidence": 2},
            }
            return {"value": values.get(tab, {})}

    pipeline = NovelAnalysisPipelineService(knowledge_service=Knowledge(), evidence_service=Evidence(), platform=Platform(), settings_service=Settings())
    task = NovelAnalysisTask(
        id="task-1", work_id="work-1", tenant_id="tenant-1", goal="复审", policy={"max_tokens_per_task": 1000},
        checkpoint={"selected_evidence_ids": ["span-1"], "reaudit_claim_ids": ["claim-1"]},
    )

    result = await pipeline.process_task(task, tenant_id="tenant-1")

    assert result.claim_ids == ("claim-1",)
    assert result.outcomes[0].claim_status == "published"
    assert pipeline._platform.groups == ["audit-route", "verify-route", "adjudicate-route"]


@pytest.mark.asyncio
async def test_reaudit_task_routes_changed_evidence_to_human_review_without_a_model_call():
    from app.application.services.novel_analysis_pipeline_service import NovelAnalysisPipelineService
    from app.domain.entities.novel_analysis_task import NovelAnalysisTask

    claim = SimpleNamespace(
        id="claim-1", work_id="work-1", subject_entity_id="宁姚", predicate="protects",
        object_entity_id="陈平安", scalar_value=None, epistemic="explicit", evidence_ids=["span-stale"],
    )

    class Knowledge:
        def get_claim(self, claim_id): return claim if claim_id == "claim-1" else None

    class Evidence:
        def get_verified_span(self, _evidence_id): return None

    class Platform:
        async def invoke_chat(self, **_kwargs):
            raise AssertionError("stale evidence must not be sent to a model")

    class Settings:
        def get_section(self, _domain, tab):
            return {"value": {"auditor_route_group": "audit-route"} if tab == "roles" else {}}

    class Decisions:
        def __init__(self): self.items = []
        def record_adjudication(self, **item): self.items.append(item)

    decisions = Decisions()
    pipeline = NovelAnalysisPipelineService(
        knowledge_service=Knowledge(), evidence_service=Evidence(), platform=Platform(), settings_service=Settings(), decision_recorder=decisions,
    )
    task = NovelAnalysisTask(
        id="task-1", work_id="work-1", tenant_id="tenant-1", goal="复审", policy={},
        checkpoint={"selected_evidence_ids": ["span-stale"], "reaudit_claim_ids": ["claim-1"]},
    )

    result = await pipeline.process_task(task, tenant_id="tenant-1")

    assert result.claim_ids == ("claim-1",)
    assert result.outcomes[0].verdict == "human_review"
    assert decisions.items[0]["role"] == "auditor"
