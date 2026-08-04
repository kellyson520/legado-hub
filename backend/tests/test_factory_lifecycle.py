import asyncio

import pytest


@pytest.mark.asyncio
async def test_scoped_novel_agent_builder_reuses_one_assembly(monkeypatch):
    import app.infrastructure.persistence.factory as factory

    monkeypatch.setattr(factory, "_scoped_novel_agent_app_service", None, raising=False)
    repository = object()
    vector_store = object()
    settings = type(
        "Settings",
        (),
        {"get_novel_settings": lambda self: {"threshold": 0.25}},
    )()
    builds = []

    async def build_repository():
        await asyncio.sleep(0)
        return repository

    def build_agent(**kwargs):
        builds.append(kwargs)
        return object()

    monkeypatch.setattr(factory, "build_novel_repository", build_repository)
    monkeypatch.setattr(factory, "build_vector_store", lambda: vector_store)
    monkeypatch.setattr(factory, "build_system_settings_service", lambda: settings)
    monkeypatch.setattr(factory, "build_novel_agent_app_service", build_agent)

    services = await asyncio.gather(
        factory.build_scoped_novel_agent_app_service(),
        factory.build_scoped_novel_agent_app_service(),
    )

    assert services[0] is services[1]
    assert len(builds) == 1
    assert builds[0]["novel_repo"] is repository
    assert builds[0]["retriever"] is factory._scoped_novel_retriever


@pytest.mark.asyncio
async def test_scoped_novel_agent_builder_can_be_reset_for_shutdown(monkeypatch):
    import app.infrastructure.persistence.factory as factory

    monkeypatch.setattr(factory, "_scoped_novel_agent_app_service", None, raising=False)
    monkeypatch.setattr(factory, "_scoped_novel_retriever", None, raising=False)
    monkeypatch.setattr(factory, "_scoped_novel_repository", None, raising=False)
    repository = object()
    monkeypatch.setattr(factory, "build_novel_repository", lambda: _return(repository))
    monkeypatch.setattr(factory, "build_vector_store", lambda: object())
    monkeypatch.setattr(
        factory,
        "build_system_settings_service",
        lambda: type("Settings", (), {"get_novel_settings": lambda self: {}})(),
    )
    created = []

    def build_agent(**kwargs):
        created.append(kwargs)
        return object()

    monkeypatch.setattr(factory, "build_novel_agent_app_service", build_agent)

    first = await factory.build_scoped_novel_agent_app_service()
    await factory.close_scoped_novel_agent_app_service()
    second = await factory.build_scoped_novel_agent_app_service()

    assert first is not second
    assert len(created) == 2


async def _return(value):
    return value
