from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-32-bytes-minimum")


DEFAULT_SOURCE_URLS = [
    "https://www.biquga.com/list/0/1.html",
    "https://www.beiquge.com/rank/",
    "https://m.biqugen.com/",
    "https://www.bqg39.cc/",
]
DEFAULT_REPORT_PATH = BACKEND_DIR / "reports" / "source-to-insight-smoke.json"


def build_acceptance_service(*, use_ai: bool = False):
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService
    from app.infrastructure.persistence.factory import (
        build_character_calibration_service,
        build_job_repository,
        build_source_build_runtime_service,
        build_source_build_service,
        build_source_complement_service,
        build_source_read_service,
        build_source_repository,
        build_source_runtime_repository,
    )

    return SourceToInsightAcceptanceService(
        source_build_service=build_source_build_service(),
        source_build_runtime=build_source_build_runtime_service(use_ai_repair=use_ai),
        job_repository=build_job_repository(),
        source_repository=build_source_repository(),
        source_runtime_repository=build_source_runtime_repository(),
        reading_service=build_source_read_service(),
        complement_service=build_source_complement_service(),
        character_service=build_character_calibration_service() if use_ai else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run source-build engine to Legado reading acceptance smoke."
    )
    parser.add_argument(
        "--fixture-mode",
        action="store_true",
        help="Marks a test/fixture run; dependency construction remains monkeypatchable.",
    )
    parser.add_argument(
        "--real-source-mode",
        action="store_true",
        help="Run against the four operator-provided real source URLs.",
    )
    parser.add_argument(
        "--source-url",
        action="append",
        default=[],
        help="Source URL to submit to source.build. May be repeated.",
    )
    parser.add_argument("--book-name", default="斗罗大陆")
    parser.add_argument("--author-hint", default="唐家三少")
    parser.add_argument("--chapter-index", type=int, default=0)
    parser.add_argument("--chapter-title", default="第一章")
    parser.add_argument(
        "--use-ai",
        action="store_true",
        help="Enable AI repair and post-read character analysis. Disabled by default.",
    )
    parser.add_argument("--tenant-id", default="source-insight-smoke")
    parser.add_argument("--output", default=str(DEFAULT_REPORT_PATH))
    args = parser.parse_args(argv)

    source_urls = args.source_url or (
        DEFAULT_SOURCE_URLS if args.real_source_mode else DEFAULT_SOURCE_URLS[:1]
    )
    scenario = {
        "source_urls": source_urls,
        "book_name": args.book_name,
        "author_hint": args.author_hint,
        "chapter_index": args.chapter_index,
        "chapter_title": args.chapter_title,
        "use_ai": args.use_ai,
        "tenant_id": args.tenant_id,
    }
    report = asyncio.run(build_acceptance_service(use_ai=args.use_ai).run(scenario))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
