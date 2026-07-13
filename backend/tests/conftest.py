import os
import sys
from pathlib import Path

import pytest


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
