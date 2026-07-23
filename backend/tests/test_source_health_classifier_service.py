from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult


def test_classifier_marks_token_missing_as_blocked_and_skipped():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=4,
        source_name="起点读书限免+本章说",
        source_url="https://www.qidian.com",
        probe_mode="search_only",
        keyword="捞尸人",
        search=StageProbeResult(
            stage="search",
            status="failed",
            request_preview="https://www.qidian.com/search?token=undefined",
            detail={"js_exec_status": "ok"},
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "blocked"
    assert decision.failure_reason == "token_missing"
    assert decision.route_policy == "skip"


def test_classifier_marks_helper_missing_as_dead():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=50,
        source_name="Pixiv 小说",
        source_url="https://www.pixiv.net",
        probe_mode="search_only",
        keyword="捞尸人",
        search=StageProbeResult(
            stage="search",
            status="failed",
            error_message="urlSearchSeries is not defined",
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "dead"
    assert decision.failure_reason == "helper_missing"


def test_classifier_marks_js_worker_failure_as_blocked_not_unknown():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=51,
        source_name="八叉书库",
        source_url="https://bcshuku.com",
        probe_mode="search_only",
        keyword="剑来",
        search=StageProbeResult(
            stage="search",
            status="failed",
            error_message="WORKER_EOF",
            detail={"js_exec_status": "fail", "js_error": "WORKER_EOF"},
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "blocked"
    assert decision.failure_reason == "js_runtime_failure"
    assert decision.route_policy == "skip"


def test_classifier_marks_cloudflare_transport_as_waf_blocked():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=67,
        source_name="和圖書",
        source_url="https://www.hetubook.com",
        probe_mode="search_only",
        keyword="捞尸人",
        search=StageProbeResult(
            stage="search",
            status="failed",
            detail={
                "http_status": 403,
                "response_kind": "html",
                "response_preview": "<title>Just a moment...</title>",
            },
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "blocked"
    assert decision.failure_reason == "waf_blocked"


def test_classifier_ignores_non_diagnostic_source_config_text_in_successful_hit():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=108,
        source_name="Lofter",
        source_url="https://api.lofter.com",
        probe_mode="full_chain",
        keyword="捞尸人",
        search=StageProbeResult(
            stage="search",
            status="ok",
            hit_count=1,
            detail={"top_hit": {"_source_config": {"bookSourceComment": "captcha login helper"}}},
        ),
        toc=StageProbeResult(stage="toc", status="failed"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "degraded"
    assert decision.failure_reason == "parse_empty"


def test_classifier_marks_zero_status_transport_as_network_unreachable():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=8,
        source_name="群U聚合",
        source_url="https://jican.x7go.top",
        probe_mode="search_only",
        keyword="捞尸人",
        search=StageProbeResult(stage="search", status="failed", detail={"http_status": 0}),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "blocked"
    assert decision.failure_reason == "network_unreachable"


def test_classifier_marks_logged_out_toc_payload_as_auth_required():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=108,
        source_name="Lofter",
        source_url="https://api.lofter.com",
        probe_mode="full_chain",
        keyword="捞尸人",
        search=StageProbeResult(stage="search", status="ok", hit_count=1),
        toc=StageProbeResult(
            stage="toc",
            status="failed",
            detail={
                "http_status": 200,
                "response_kind": "json",
                "response_preview": '{"meta":{"status":4200,"msg":"用户已注销或设置仅自己可见"}}',
            },
        ),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "blocked"
    assert decision.failure_reason == "auth_required"


def test_classifier_marks_non_waf_http_status_as_http_status_error():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=30,
        source_name="http error source",
        source_url="https://example.test",
        probe_mode="search_only",
        keyword="sample",
        search=StageProbeResult(
            stage="search",
            status="failed",
            detail={"http_status": 503, "response_kind": "html"},
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "blocked"
    assert decision.failure_reason == "http_status_error"


def test_classifier_marks_html_response_when_json_is_expected():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=108,
        source_name="html replacement source",
        source_url="https://example.test",
        probe_mode="search_only",
        keyword="sample",
        search=StageProbeResult(
            stage="search",
            status="failed",
            detail={
                "http_status": 200,
                "response_kind": "html",
                "expected_response_kind": "json",
                "response_preview": "<html>upstream replacement</html>",
            },
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "degraded"
    assert decision.failure_reason == "html_instead_of_json"


def test_classifier_marks_verification_wall_as_waf_blocked():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=109,
        source_name="验证墙书源",
        source_url="https://verify.example",
        probe_mode="full_chain",
        keyword="sample",
        search=StageProbeResult(stage="search", status="ok", hit_count=1),
        toc=StageProbeResult(stage="toc", status="ok", hit_count=1),
        content=StageProbeResult(
            stage="content",
            status="failed",
            detail={"parse_status": "content_access_blocked", "block_reason": "verification_wall"},
        ),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "blocked"
    assert decision.failure_reason == "waf_blocked"


def test_classifier_keeps_probe_with_no_keyword_hit_unknown_without_transport_evidence():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=1,
        source_name="无结果书源",
        source_url="https://example.test",
        probe_mode="full_chain",
        keyword="捞尸人",
        search=StageProbeResult(stage="search", status="failed", hit_count=0),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.failure_reason == "keyword_no_result"
    assert decision.health_status == "unknown"
    assert decision.route_policy == "probe_only"
    assert decision.decision_confidence == "low"


def test_classifier_ignores_valid_js_request_preview_when_search_has_no_hits():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=2,
        source_name="合法空结果 JS 书源",
        source_url="https://example.test",
        probe_mode="search_only",
        keyword="不存在的关键词",
        search=StageProbeResult(
            stage="search",
            status="failed",
            hit_count=0,
            request_preview="https://api.example.test/search?q=%E4%B8%8D%E5%AD%98%E5%9C%A8%E7%9A%84%E5%85%B3%E9%94%AE%E8%AF%8D",
            detail={
                "js_exec_status": "ok",
                "js_result_preview": "https://api.example.test/search",
                "http_status": 200,
                "response_kind": "json",
            },
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.failure_reason == "keyword_no_result"
    assert decision.health_status == "unknown"
    assert decision.route_policy == "probe_only"


def test_classifier_does_not_treat_captcha_word_in_valid_json_as_a_verification_wall():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=5,
        source_name="合法 JSON 书源",
        source_url="https://example.test",
        probe_mode="search_only",
        keyword="不存在的关键词",
        search=StageProbeResult(
            stage="search",
            status="failed",
            hit_count=0,
            detail={
                "http_status": 200,
                "response_kind": "json",
                "response_preview": '{"data": [], "note": "captcha is mentioned in metadata"}',
            },
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.failure_reason == "keyword_no_result"
    assert decision.health_status == "unknown"


def test_classifier_does_not_call_full_chain_healthy_when_later_stages_were_skipped():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=3,
        source_name="链路未完成书源",
        source_url="https://example.test",
        probe_mode="full_chain",
        keyword="sample",
        search=StageProbeResult(stage="search", status="ok", hit_count=1),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status != "healthy"
    assert decision.route_policy != "allow"


def test_classifier_does_not_allow_unknown_probe_mode_to_be_healthy():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=4,
        source_name="非法模式书源",
        source_url="https://example.test",
        probe_mode="full_chain ",
        keyword="sample",
        search=StageProbeResult(stage="search", status="ok", hit_count=1),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status != "healthy"
    assert decision.route_policy != "allow"


def test_classifier_marks_diagnostic_gap_as_degraded_not_unknown():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=2,
        source_name="诊断不足书源",
        source_url="https://example.test",
        probe_mode="full_chain",
        keyword="捞尸人",
        search=StageProbeResult(
            stage="search",
            status="failed",
            error_message="parser returned no structured evidence",
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.failure_reason == "unknown_error"
    assert decision.health_status == "degraded"
    assert decision.decision_confidence == "low"
