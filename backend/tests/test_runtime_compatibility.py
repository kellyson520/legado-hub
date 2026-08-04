from pathlib import Path


def test_logging_uses_a_writable_default_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("LOG_DIR", raising=False)

    from app.core.logging import resolve_log_dir

    log_dir = resolve_log_dir(tmp_path)

    assert log_dir.is_relative_to(tmp_path)


def test_interactive_browser_state_is_a_string_enum_on_python_310():
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    assert str(InteractiveBrowserState.PENDING) == "pending"
