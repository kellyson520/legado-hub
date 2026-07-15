def test_interactive_browser_factory_reuses_one_in_process_supervisor(monkeypatch):
    from app.infrastructure.persistence import factory

    constructed = []

    class StubService:
        def __init__(self, **kwargs):
            constructed.append(kwargs)

    monkeypatch.setattr(factory, 'InteractiveBrowserService', StubService)
    monkeypatch.setattr(factory, 'PlaywrightBrowserDriver', lambda **kwargs: ('driver', kwargs))
    monkeypatch.setattr(factory, 'build_interactive_browser_repository', lambda: 'repo')
    monkeypatch.setattr(factory, 'build_system_settings_service', lambda: 'settings')
    monkeypatch.setattr(factory, '_interactive_browser_service_singleton', None, raising=False)

    first = factory.build_interactive_browser_service()
    second = factory.build_interactive_browser_service()

    assert first is second
    assert len(constructed) == 1
    assert constructed[0]['repo'] == 'repo'
    assert constructed[0]['settings'] == 'settings'


def test_interactive_browser_factory_caches_supervisor_facade_instead_of_bare_service(monkeypatch):
    from app.infrastructure.persistence import factory

    constructed = []

    class StubSupervisor:
        def __init__(self, service_factory):
            constructed.append(service_factory)

    monkeypatch.setattr(factory, 'InteractiveBrowserSupervisor', StubSupervisor)
    monkeypatch.setattr(factory, '_interactive_browser_service_singleton', None, raising=False)

    supervisor = factory.build_interactive_browser_service()

    assert isinstance(supervisor, StubSupervisor)
    assert len(constructed) == 1
    assert callable(constructed[0])


def test_close_interactive_browser_supervisor_closes_only_the_cached_instance_and_is_idempotent(monkeypatch):
    from app.infrastructure.persistence import factory

    closed = []

    class StubSupervisor:
        def close(self):
            closed.append('closed')

    supervisor = StubSupervisor()
    monkeypatch.setattr(factory, '_interactive_browser_service_singleton', supervisor, raising=False)

    factory.close_interactive_browser_supervisor()
    factory.close_interactive_browser_supervisor()

    assert closed == ['closed']
    assert factory._interactive_browser_service_singleton is None
