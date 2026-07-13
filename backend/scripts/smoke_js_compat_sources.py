from pathlib import Path
import asyncio
import os
import sys
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-32-bytes-minimum")

from app.infrastructure.persistence.factory import (
    build_source_health_admin_service,
    build_source_read_service,
)
from app.infrastructure.legado.engine import UrlUtils


DEFAULT_KEYWORDS = ["捞尸人", "斗罗大陆"]


async def main():
    service = build_source_read_service()
    admin_service = build_source_health_admin_service()
    try:
        sources = await service._repo.list_book_sources_full(enabled_only=True)
        js_sources = [
            item for item in sources
            if str(item.get("searchUrl", "") or "").strip().startswith("@js:")
        ][:10]

        print(f"[js-compat] selected_sources={len(js_sources)}")
        for source in js_sources:
            probe = await admin_service.probe_book_source(
                source["id"],
                keyword_samples=[DEFAULT_KEYWORDS[0]],
                probe_mode="search_only",
            )
            snapshot = probe["snapshot"]
            search_js = str(source.get("searchUrl", "") or "").strip()[4:].strip()
            search_key = (
                DEFAULT_KEYWORDS[0]
                if service._fetcher.js_search_prefers_raw_key(search_js)
                else quote(DEFAULT_KEYWORDS[0])
            )
            js_output = service._fetcher._js_runtime.execute_with_metadata(
                search_js,
                data=None,
                stage="search_url_js",
                source=source,
                baseUrl=UrlUtils.get_base_url(source.get("bookSourceUrl", "")),
                variables={
                    "keyword": DEFAULT_KEYWORDS[0],
                    "key": search_key,
                    "searchKey": search_key,
                    "searchkey": search_key,
                    "page": 1,
                },
                headers=UrlUtils.parse_headers(source.get("header", "")),
            )
            print(
                f"[js-compat] source_id={source['id']} "
                f"name={source.get('bookSourceName', '')} "
                f"health={snapshot['health_status']} "
                f"reason={snapshot['failure_reason']} "
                f"search={snapshot['search_status']} "
                f"toc={snapshot['toc_status']} "
                f"content={snapshot['content_status']} "
                f"exec={'ok' if js_output.success else 'fail'} "
                f"preview={str(js_output.value)[:120] if js_output.success else js_output.error}"
            )
            for keyword in DEFAULT_KEYWORDS:
                try:
                    result = await service.search_books(
                        keyword=keyword,
                        source_ids=[source["id"]],
                        limit_per_source=1,
                    )
                    print(
                        f"  - keyword={keyword} "
                        f"hits={len(result['items'])}"
                    )
                except Exception as exc:
                    print(
                        f"  - keyword={keyword} "
                        f"error={type(exc).__name__}: {exc}"
                    )
    finally:
        await admin_service.aclose()
        await service._fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
