from pathlib import Path


def test_api_dockerfile_is_slim_non_root_and_single_worker():
    dockerfile = Path(__file__).parents[1].joinpath("Dockerfile").read_text()

    assert "FROM python:3.11-slim-bookworm AS builder" in dockerfile
    assert "ARG PIP_INDEX_URL" in dockerfile
    assert "https://pypi.org/simple" in dockerfile
    assert "USER app" in dockerfile
    assert "apt-get" not in dockerfile
    assert "gradle" not in dockerfile.lower()
    assert "openjdk" not in dockerfile.lower()
    assert "chromium" not in dockerfile.lower()


def test_compose_disables_optional_native_runtime_in_slim_api():
    compose = Path(__file__).parents[1].joinpath("..", "docker-compose.yml").read_text()
    assert "LEGADO_RUNTIME_HEALTHCHECK_ENABLED: \"false\"" in compose
