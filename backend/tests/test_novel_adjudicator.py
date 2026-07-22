import json

import pytest


def _candidate(*, name="江轩", score=0.5, status="candidate"):
    from app.application.services.novel_understanding.candidate_extractor import (
        CandidateEvidence,
        LocalCandidate,
    )
    from app.domain.entities.novel import EntityType

    return LocalCandidate(
        name=name,
        entity_type=EntityType.CHARACTER,
        score=score,
        mentions=1,
        status=status,
        evidence=[CandidateEvidence(3, 0, 2, 12, f"正文提到{name}")],
    )


@pytest.mark.asyncio
async def test_high_confidence_local_candidate_is_accepted_without_provider_call():
    from app.application.services.novel_understanding.adjudicator import NovelAdjudicator

    class Provider:
        calls = 0

        async def invoke_novel_adjudicate(self, **kwargs):
            self.calls += 1
            return {}

    provider = Provider()
    result = await NovelAdjudicator(provider=provider).adjudicate("user:1", 7, [_candidate(score=0.96, status="confirmed")])

    assert result[0]["verdict"] == "accept"
    assert result[0]["source"] == "local"
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_ambiguous_candidates_are_sent_in_one_bounded_evidence_only_request():
    from app.application.services.novel_understanding.adjudicator import NovelAdjudicator

    class Provider:
        def __init__(self):
            self.calls = []

        async def invoke_novel_adjudicate(self, **kwargs):
            self.calls.append(kwargs)
            payload = kwargs["payload"]
            evidence_id = payload["candidates"][0]["evidence"][0]["id"]
            return {"output": {"text": json.dumps({"decisions": [{"index": 0, "verdict": "accept", "evidence_ids": [evidence_id]}]})}}

    provider = Provider()
    result = await NovelAdjudicator(provider=provider, max_evidence_chars=24).adjudicate(
        "user:1", 7, [_candidate(), _candidate(name="周宁")]
    )

    assert len(provider.calls) == 1
    sent = provider.calls[0]["payload"]
    assert "chapter_text" not in json.dumps(sent, ensure_ascii=False)
    assert all(len(item["text"]) <= 24 for item in sent["candidates"][0]["evidence"])
    assert result[0]["verdict"] == "accept"
    assert result[1]["verdict"] == "pending"


@pytest.mark.asyncio
async def test_provider_failure_keeps_indexing_with_pending_decisions():
    from app.application.services.novel_understanding.adjudicator import NovelAdjudicator

    class Provider:
        async def invoke_novel_adjudicate(self, **kwargs):
            raise RuntimeError("route unavailable")

    result = await NovelAdjudicator(provider=Provider()).adjudicate("user:1", 7, [_candidate(), _candidate(name="周宁")])

    assert [item["verdict"] for item in result] == ["pending", "pending"]
    assert all("route unavailable" in item["reason"] for item in result)


@pytest.mark.asyncio
async def test_agent_cannot_accept_with_an_evidence_id_outside_the_request():
    from app.application.services.novel_understanding.adjudicator import NovelAdjudicator

    class Provider:
        async def invoke_novel_adjudicate(self, **kwargs):
            return {"output": {"text": json.dumps({"decisions": [{"index": 0, "verdict": "accept", "evidence_ids": ["not-sent"]}]})}}

    result = await NovelAdjudicator(provider=Provider()).adjudicate("user:1", 7, [_candidate()])

    assert result[0]["verdict"] == "pending"
    assert "evidence" in result[0]["reason"]


@pytest.mark.asyncio
async def test_ambiguous_decision_is_persisted_as_a_bounded_candidate_record():
    from app.application.services.novel_understanding.adjudicator import NovelAdjudicator

    class Provider:
        async def invoke_novel_adjudicate(self, **kwargs):
            evidence_id = kwargs["payload"]["candidates"][0]["evidence"][0]["id"]
            return {"output": {"text": json.dumps({"decisions": [{"index": 0, "verdict": "accept", "evidence_ids": [evidence_id]}]})}}

    class CandidateRepo:
        def __init__(self):
            self.saved = []
            self.updated = []

        async def upsert_adjudication_candidate(self, candidate):
            self.saved.append(candidate)
            candidate.id = len(self.saved)
            return candidate

        async def update_adjudication_candidate(self, owner_scope, candidate_id, **kwargs):
            self.updated.append((owner_scope, candidate_id, kwargs))
            return True

    repo = CandidateRepo()
    result = await NovelAdjudicator(provider=Provider(), repo=repo).adjudicate("user:1", 7, [_candidate()])

    assert result[0]["verdict"] == "accept"
    assert len(repo.saved) == 1
    assert repo.saved[0].evidence_payload[0]["text"] == "正文提到江轩"
    assert repo.updated[0][1] == 1
    assert repo.updated[0][2]["status"] == "accept"
