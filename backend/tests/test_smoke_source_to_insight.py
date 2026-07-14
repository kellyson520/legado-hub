import json


def test_smoke_cli_writes_report_from_fixture_service(tmp_path, monkeypatch):
    from scripts import smoke_source_to_insight

    report_path = tmp_path / "report.json"

    class FakeService:
        async def run(self, scenario):
            return {
                "scenario": scenario,
                "status": "passed",
                "steps": [],
                "source_builds": [{"url": "https://a.test", "status": "passed"}],
                "book_candidates": [],
                "toc_candidates": [],
                "chapter_candidates": [],
                "complement": {},
                "insights": {"characters": [], "relations": [], "plot_events": [], "world_rules": [], "timeline": []},
                "knowledge_proposals": [],
                "ai": {"used": False, "status": "skipped", "provider": "", "model": "", "usage": {}},
            }

    monkeypatch.setattr(
        smoke_source_to_insight,
        "build_acceptance_service",
        lambda use_ai=False: FakeService(),
    )

    exit_code = smoke_source_to_insight.main([
        "--fixture-mode",
        "--output",
        str(report_path),
        "--book-name",
        "斗罗大陆",
        "--source-url",
        "https://a.test",
    ])

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["source_builds"][0]["url"] == "https://a.test"
    assert report["scenario"]["source_urls"] == ["https://a.test"]


def test_smoke_cli_returns_nonzero_for_partial_acceptance(tmp_path, monkeypatch):
    from scripts import smoke_source_to_insight

    class FakeService:
        async def run(self, scenario):
            return {"scenario": scenario, "status": "partial"}

    monkeypatch.setattr(
        smoke_source_to_insight,
        "build_acceptance_service",
        lambda use_ai=False: FakeService(),
    )

    exit_code = smoke_source_to_insight.main([
        "--fixture-mode",
        "--output",
        str(tmp_path / "partial.json"),
    ])

    assert exit_code == 1
