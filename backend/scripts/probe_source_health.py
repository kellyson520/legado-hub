from pathlib import Path
import argparse
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

from app.infrastructure.persistence.factory import build_source_health_admin_service


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-ids", nargs="+", type=int, required=True)
    parser.add_argument("--keywords", nargs="+", default=["捞尸人", "斗罗大陆"])
    parser.add_argument("--probe-mode", default="full_chain")
    args = parser.parse_args()

    service = build_source_health_admin_service()
    try:
        result = await service.probe_book_sources(
            args.source_ids,
            keyword_samples=args.keywords,
            probe_mode=args.probe_mode,
        )
        print(f"[source-health] total={result['total']}")
        for item in result["results"]:
            snapshot = item["snapshot"]
            print(
                f"  - source_id={snapshot['source_id']} "
                f"status={snapshot['health_status']} "
                f"search={snapshot['search_status']} toc={snapshot['toc_status']} content={snapshot['content_status']} "
                f"reason={snapshot['failure_reason']} policy={snapshot['route_policy']}"
            )
    finally:
        await service.aclose()


if __name__ == "__main__":
    asyncio.run(main())
