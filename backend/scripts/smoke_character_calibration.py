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

from app.infrastructure.persistence.factory import (
    build_character_calibration_service,
    build_source_read_service,
)


async def _load_excerpt(service, keyword: str, source_id: int, author_hint: str | None = None) -> dict | None:
    result = await service.search_books(
        keyword=keyword,
        source_ids=[source_id],
        limit_per_source=1,
        author_hint=author_hint,
    )
    if not result["items"]:
        return None

    book = result["items"][0]
    toc = await service.get_book_toc(source_id=source_id, book_url=book["bookUrl"])
    if not toc["chapters"]:
        return None

    content = await service.get_chapter_content(source_id=source_id, chapter_url=toc["chapters"][0]["url"])
    excerpt = (content.get("content") or "")[:500]
    return {
        "source_id": source_id,
        "name": book["name"],
        "author": book["author"],
        "excerpt": excerpt,
    }


async def main():
    read_service = build_source_read_service()
    calibration_service = build_character_calibration_service()
    try:
        items = []
        for source_id, author_hint in [(7, "陈十三"), (33, None)]:
            item = await _load_excerpt(read_service, "捞尸人", source_id, author_hint=author_hint)
            if item:
                items.append(item)

        result = await calibration_service.calibrate(keyword="捞尸人", items=items)
        print(f"[character] items: {len(result['items'])}")
        for item in result["items"]:
            print(
                f"  - source_id={item.get('source_id')} {item.get('name')} / {item.get('author')} "
                f"characters={item.get('characters')}"
            )
        print(f"[character] pairwise: {result['pairwise']}")
        print(f"[character] used_provider: {result['used_provider']}")
    finally:
        await read_service._fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
