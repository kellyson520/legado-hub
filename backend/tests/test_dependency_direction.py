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


def test_infrastructure_persistence_does_not_import_legacy_database_module():
    root = Path(__file__).resolve().parents[1] / "app" / "infrastructure"
    violations = []
    for path in root.rglob("*.py"):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "from app.database" in line or "import app.database" in line:
                violations.append(f"{path}:{line_no}: {line.strip()}")

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
