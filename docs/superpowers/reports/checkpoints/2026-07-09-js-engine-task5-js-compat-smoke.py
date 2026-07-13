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


async def main():
    service = build_source_read_service()
    try:
        sources = await service._repo.list_book_sources_full(enabled_only=True)
        js_sources = [
            item for item in sources
            if str(item.get("searchUrl", "") or "").strip().startswith("@js:")
        ][:10]

        print(f"[js-compat] selected_sources={len(js_sources)}")
        for source in js_sources:
            print(
                f"[js-compat] source_id={source['id']} "
                f"name={source.get('bookSourceName', '')}"
            )
            for keyword in DEFAULT_KEYWORDS:
                result = await service.search_books(
                    keyword=keyword,
                    source_ids=[source["id"]],
                    limit_per_source=1,
                )
                print(
                    f"  - keyword={keyword} "
                    f"hits={len(result['items'])}"
                )
    finally:
        await service._fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
