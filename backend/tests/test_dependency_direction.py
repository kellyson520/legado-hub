from pathlib import Path


def test_domain_and_application_layers_do_not_import_infrastructure():
    root = Path(__file__).resolve().parents[1] / "app"
    violations = []
    for layer in ("domain", "application"):
        for path in (root / layer).rglob("*.py"):
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if "from app.infrastructure" in line or "import app.infrastructure" in line:
                    violations.append(f"{path}:{line_no}: {line.strip()}")

    assert violations == []


def test_domain_layer_is_framework_and_application_free():
    root = Path(__file__).resolve().parents[1] / "app" / "domain"
    forbidden = (
        "from app.core",
        "import app.core",
        "from app.application",
        "import app.application",
        "from app.infrastructure",
        "import app.infrastructure",
        "from ..core",
        "from ...core",
        "from ..application",
        "from ...application",
    )
    violations = []
    for path in root.rglob("*.py"):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(forbidden):
                violations.append(f"{path}:{line_no}: {stripped}")

    assert violations == []


def test_core_layer_does_not_import_application_or_infrastructure():
    root = Path(__file__).resolve().parents[1] / "app" / "core"
    violations = []
    forbidden = (
        "from app.application",
        "import app.application",
        "from app.infrastructure",
        "import app.infrastructure",
        "from ..application",
        "from ..infrastructure",
    )
    for path in root.rglob("*.py"):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip().startswith(forbidden):
                violations.append(f"{path}:{line_no}: {line.strip()}")

    assert violations == []


def test_infrastructure_persistence_does_not_import_legacy_database_module():
    root = Path(__file__).resolve().parents[1] / "app" / "infrastructure"
    violations = []
    for path in root.rglob("*.py"):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "from app.database" in line or "import app.database" in line:
                violations.append(f"{path}:{line_no}: {line.strip()}")

    assert violations == []


def test_infrastructure_adapters_depend_on_ports_not_application_services():
    root = Path(__file__).resolve().parents[1] / "app" / "infrastructure"
    violations = []
    for path in root.rglob("*.py"):
        # The persistence factory is the composition root by design. SQLite
        # bootstrap only reads a port-level provider constant.
        if path.name == "factory.py" or path.name == "bootstrap.py":
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("from app.application.services", "import app.application.services")):
                violations.append(f"{path}:{line_no}: {stripped}")

    assert violations == []


def test_legacy_database_module_is_only_a_compatibility_facade():
    database_module = (Path(__file__).resolve().parents[1] / "app" / "database.py").read_text(
        encoding="utf-8"
    )

    assert "from app.infrastructure.persistence.sqlite.session import" in database_module
    assert "create_engine(" not in database_module


def test_application_services_do_not_import_legacy_services_package():
    root = Path(__file__).resolve().parents[1] / "app" / "application"
    violations = []
    for path in root.rglob("*.py"):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "from app.services" in line or "import app.services" in line:
                violations.append(f"{path}:{line_no}: {line.strip()}")

    assert violations == []


def test_active_production_modules_do_not_import_legacy_services_namespace():
    app_root = Path(__file__).resolve().parents[1] / "app"
    violations = []
    for path in app_root.rglob("*.py"):
        if "services" in path.relative_to(app_root).parts:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "from app.services" in line or "import app.services" in line:
                violations.append(f"{path}:{line_no}: {line.strip()}")

    assert violations == []


def test_legacy_route_trees_are_retired_from_the_source_tree():
    app_root = Path(__file__).resolve().parents[1] / "app"
    legacy_trees = (
        app_root / "api" / "routers",
        app_root / "routers",
        app_root / "interfaces" / "api",
    )

    remaining_sources = [
        str(path)
        for tree in legacy_trees
        for path in tree.rglob("*.py")
        if path.is_file()
    ]

    assert remaining_sources == []


def test_scheduler_does_not_import_legacy_services_package():
    scheduler = (Path(__file__).resolve().parents[1] / "app" / "tasks" / "scheduler.py").read_text(
        encoding="utf-8"
    )

    assert "from ..services" not in scheduler
    assert "from app.services" not in scheduler


def test_non_core_modules_use_the_structured_logger_facade():
    root = Path(__file__).resolve().parents[1] / "app"
    violations = []
    for path in root.rglob("*.py"):
        if path.parts[-2:] == ("core", path.name):
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "logging.getLogger(" in line:
                violations.append(f"{path}:{line_no}: {line.strip()}")

    assert violations == []


def test_domain_and_application_layers_do_not_import_concrete_transport_or_orms():
    root = Path(__file__).resolve().parents[1] / "app"
    violations = []
    forbidden_prefixes = (
        "import httpx",
        "from httpx",
        "import aiohttp",
        "from aiohttp",
        "import requests",
        "from requests",
        "import sqlalchemy",
        "from sqlalchemy",
        "import playwright",
        "from playwright",
    )
    for layer in ("domain", "application"):
        for path in (root / layer).rglob("*.py"):
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith(forbidden_prefixes):
                    violations.append(f"{path}:{line_no}: {stripped}")

    assert violations == []


def test_scheduler_uses_canonical_sqlite_session_path():
    scheduler = (Path(__file__).resolve().parents[1] / "app" / "tasks" / "scheduler.py").read_text(
        encoding="utf-8"
    )

    assert "from ..database import" not in scheduler
    assert "from app.database import" not in scheduler


def test_scheduler_delegates_storage_mutations_to_application_services():
    scheduler = (Path(__file__).resolve().parents[1] / "app" / "tasks" / "scheduler.py").read_text(
        encoding="utf-8"
    )

    forbidden = (
        "SessionLocal",
        "BookSourceModel",
        "RssSourceModel",
        "ApiKeyModel",
        "QuotaUsageModel",
    )
    assert not any(name in scheduler for name in forbidden)


def test_unmounted_legacy_sqlite_repositories_are_retired():
    sqlite_root = Path(__file__).resolve().parents[1] / "app" / "infrastructure" / "persistence" / "sqlite"

    assert not (sqlite_root / "user_repo_impl.py").exists()
    assert not (sqlite_root / "translation_repo_impl.py").exists()
