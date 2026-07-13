from pathlib import Path
import asyncio
import os
import sys


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-32-bytes-minimum")

from app.infrastructure.persistence.factory import (
    build_source_complement_service,
    build_source_read_service,
)


async def _resolve_first_chapter(service, keyword: str, source_id: int) -> dict | None:
    search_result = await service.search_books(keyword=keyword, source_ids=[source_id], limit_per_source=3)
    if not search_result["items"]:
        return None

    selected = search_result["items"][0]
    toc = await service.get_book_toc(source_id=source_id, book_url=selected["bookUrl"])
    if not toc["chapters"]:
        return None

    first = toc["chapters"][0]
    return {
        "source_id": source_id,
        "source_name": selected["sourceName"],
        "source_url": selected["sourceUrl"],
        "book_name": selected["name"],
        "chapter_title": first["title"],
        "chapter_num": 1,
        "chapter_url": first["url"],
    }


async def main():
    read_service = build_source_read_service()
    complement_service = build_source_complement_service()
    try:
        candidates = []
        for source_id in [7, 33]:
            candidate = await _resolve_first_chapter(read_service, "捞尸人", source_id)
            if candidate:
                candidates.append(candidate)

        if not candidates:
            print("[complement] no chapter candidates resolved")
            return

        result = await complement_service.complement_chapter_candidates(
            book_name=candidates[0]["book_name"],
            chapter_title=candidates[0]["chapter_title"],
            chapter_num=candidates[0]["chapter_num"],
            items=[
                {
                    "source_id": item["source_id"],
                    "chapter_url": item["chapter_url"],
                    "source_name": item["source_name"],
                    "source_url": item["source_url"],
                }
                for item in candidates
            ],
        )

        print(f"[complement] inputs: {len(candidates)}")
        print(f"[complement] status: {result['status']}")
        print(f"[complement] successful_sources: {result['successful_sources']}")
        print(f"[complement] merged_from: {result['merged_from']}")
        print(f"[complement] quality_score: {result['quality_score']}")
        print(f"[complement] final_word_count: {result['final_word_count']}")
        print(result["final_content"][:500])
    finally:
        await read_service._fetcher.close()
        await complement_service.aclose()


if __name__ == "__main__":
    asyncio.run(main())
