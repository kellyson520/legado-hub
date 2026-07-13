from pathlib import Path
import asyncio
import os
import sys


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-32-bytes-minimum")

from app.infrastructure.persistence.factory import build_source_read_service


DEFAULT_KEYWORDS = ["捞尸人", "斗罗大陆"]
DEFAULT_SOURCE_IDS = [7, 12, 33]
DEFAULT_AUTHOR_HINTS = {
    "捞尸人": "陈十三",
    "斗罗大陆": "唐家三少",
}


async def main():
    service = build_source_read_service()
    try:
        source_rows = await service._repo.list_book_sources_full(ids=DEFAULT_SOURCE_IDS)
        source_map = {row["id"]: row for row in source_rows}

        print(f"[search] source_ids: {DEFAULT_SOURCE_IDS}")
        for source_id in DEFAULT_SOURCE_IDS:
            source = source_map.get(source_id, {})
            search_url = str(source.get("searchUrl", "") or "")
            js_mode = "js" if search_url.strip().startswith("@js:") else "plain"
            print(
                f"[search] source_id={source_id} "
                f"name={source.get('bookSourceName', '')} "
                f"mode={js_mode}"
            )

        print(f"[search] keywords: {DEFAULT_KEYWORDS}")
        for keyword in DEFAULT_KEYWORDS:
            result = await service.search_books(
                keyword=keyword,
                source_ids=DEFAULT_SOURCE_IDS,
                limit_per_source=3,
                author_hint=DEFAULT_AUTHOR_HINTS.get(keyword),
                routing_mode="auto",
                include_health=True,
            )
            print(f"[search] keyword={keyword} hits={len(result['items'])} route={result['route_summary']}")
            for item in result["items"][:10]:
                source = source_map.get(item["source_id"], {})
                search_url = str(source.get("searchUrl", "") or "")
                js_mode = "js" if search_url.strip().startswith("@js:") else "plain"
                print(
                    f"  - [source_id={item['source_id']}] "
                    f"[{item['sourceName']}] "
                    f"{item['name']} / {item['author']} "
                    f"(mode={js_mode}, compat=baseline, "
                    f"health={item.get('health_status')}, "
                    f"decision={item.get('route_decision')}, "
                    f"reason={item.get('failure_reason') or '-'})"
                )
    finally:
        await service._fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
