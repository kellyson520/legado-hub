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


@pytest_asyncio.fixture
async def started_event_bus():
    from app.core.events import MemoryEventBus

    bus = MemoryEventBus()
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()
