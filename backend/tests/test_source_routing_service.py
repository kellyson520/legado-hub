from app.domain.entities.source_health import SourceHealthSnapshot


def test_routing_service_skips_blocked_and_prefers_plain_healthy_sources():
    from app.application.services.source_routing_service import SourceRoutingService

    sources = [
        {
            "id": 1,
            "bookSourceName": "Plain Healthy",
            "bookSourceUrl": "https://a.example.com",
            "searchUrl": "https://a.example.com/search?key={{key}}",
        },
        {
            "id": 2,
            "bookSourceName": "JS Blocked",
            "bookSourceUrl": "https://b.example.com",
            "searchUrl": "@js:return 'https://b.example.com'",
        },
        {
            "id": 3,
            "bookSourceName": "JS Degraded",
            "bookSourceUrl": "https://c.example.com",
            "searchUrl": "@js:return 'https://c.example.com'",
        },
    ]
    snapshots = {
        1: SourceHealthSnapshot(
            source_id=1,
            source_name="Plain Healthy",
            source_url="https://a.example.com",
            health_status="healthy",
            route_policy="allow",
            route_score=100,
        ),
        2: SourceHealthSnapshot(
            source_id=2,
            source_name="JS Blocked",
            source_url="https://b.example.com",
            health_status="blocked",
            failure_reason="token_missing",
            route_policy="skip",
            route_score=0,
        ),
        3: SourceHealthSnapshot(
            source_id=3,
            source_name="JS Degraded",
            source_url="https://c.example.com",
            health_status="degraded",
            failure_reason="upstream_changed",
            route_policy="deprioritize",
            route_score=40,
        ),
    }

    ranked = SourceRoutingService().rank_search_sources(sources, snapshots, routing_mode="auto")

    assert [item["source"]["id"] for item in ranked] == [1, 3]
    assert ranked[0]["decision"]["route_decision"] == "allow"
    assert ranked[1]["decision"]["route_decision"] == "deprioritize"
