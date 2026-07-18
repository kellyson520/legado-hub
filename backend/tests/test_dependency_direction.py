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
