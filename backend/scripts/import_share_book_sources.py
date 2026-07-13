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

from app.infrastructure.persistence.factory import build_source_service


DEFAULT_FILE = ROOT / "测试源" / "shareBookSource.json"


async def main():
    service = build_source_service()
    result = await service.import_book_sources_from_file(str(DEFAULT_FILE), actor_id=1, replace_existing=True)
    print(f"[import] using file: {DEFAULT_FILE}")
    print(f"[import] imported book sources: {result['book_count']}")


if __name__ == "__main__":
    asyncio.run(main())
