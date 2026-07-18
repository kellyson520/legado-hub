from typing import Any

from app.application.services.interactive_browser_service import BrowserValidationResult
from app.application.services.source_probe_service import SourceProbeService
from app.infrastructure.browser.browser_http_client import BrowserHttpClient
from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher


async def run_browser_probe(handle: Any, source_rule: dict, keyword: str) -> BrowserValidationResult:
    source = {**source_rule}
    source.setdefault("id", 0)
    probe = SourceProbeService(
        fetcher=LegadoBookSourceFetcher(
            http_client=BrowserHttpClient(
                page=handle.page,
                allowed_origins=set(handle.allowed_origins),
            )
        )
    )
    try:
        evidence = await probe.probe_source(source, keyword_samples=[keyword], probe_mode="full_chain")
    finally:
        await probe.aclose()
    stages = {
        "search": {"status": evidence.search.status, "hit_count": evidence.search.hit_count},
        "toc": {"status": evidence.toc.status, "hit_count": evidence.toc.hit_count},
        "content": {
            "status": evidence.content.status,
            "content_length": int(evidence.content.detail.get("content_length", 0) or 0),
        },
    }
    if evidence.content.detail.get("block_reason") == "verification_wall":
        return BrowserValidationResult.failed("verification_required", stages)
    if evidence.search.status != "ok" or evidence.search.hit_count < 1:
        return BrowserValidationResult.failed("search_failed", stages)
    if evidence.toc.status != "ok" or evidence.toc.hit_count < 1:
        return BrowserValidationResult.failed("toc_failed", stages)
    if evidence.content.status != "ok" or stages["content"]["content_length"] < 80:
        return BrowserValidationResult.failed("content_failed", stages)
    return BrowserValidationResult.passed(stages)
