import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-bytes-minimum")


MODULE_PREFIXES = (
    "app.main",
    "app.database",
    "app.core.config",
    "app.core.security",
    "app.core.exception_handlers",
    "app.core.permissions",
    "app.interfaces.api",
    "app.interfaces.http",
    "app.infrastructure.persistence",
    "app.application.services",
)


@pytest.fixture(autouse=True)
def reload_app_modules():
    for name in list(sys.modules):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in MODULE_PREFIXES):
            sys.modules.pop(name, None)
    yield


@pytest.fixture
def fresh_event_bus():
    from app.core.events import MemoryEventBus

    return MemoryEventBus()


@pytest.fixture
def cache_provider():
    from app.infrastructure.cache.memory_cache import MemoryCacheProvider

    return MemoryCacheProvider()


@pytest.fixture
def sample_book_source_data():
    return {
        "bookSourceUrl": "https://example.com",
        "bookSourceName": "测试书源",
        "enabled": True,
        "sourceStatus": "ok",
    }


@pytest.fixture
def sample_rss_source_data():
    return {
        "sourceUrl": "https://rss.example.com/feed.xml",
        "sourceName": "测试RSS源",
        "enabled": True,
        "sourceStatus": "ok",
    }


@pytest.fixture
def sample_subscription_data():
    return {
        "id": 1,
        "name": "测试订阅",
        "url": "https://example.com/source",
        "subType": "book",
        "enabled": True,
    }


@pytest_asyncio.fixture
async def started_event_bus():
    from app.core.events import MemoryEventBus

    bus = MemoryEventBus()
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()
