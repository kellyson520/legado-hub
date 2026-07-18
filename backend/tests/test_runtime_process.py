from app.infrastructure.legado.engine.native_models import RuntimeResult
from app.infrastructure.legado.engine.runtime_process import RuntimeProcessManager


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.closed = False
        self.pings = 0

    def ping(self):
        self.pings += 1
        return self.result

    def close(self):
        self.closed = True


def test_manager_reports_ready_runtime():
    client = FakeClient(RuntimeResult(success=True, value="pong", trace={"engine": "fake"}))
    manager = RuntimeProcessManager(client)

    status = manager.health()

    assert status["state"] == "ready"
    assert status["engine"] == "fake"
    assert client.pings == 1


def test_manager_reports_unavailable_runtime_and_closes_client():
    client = FakeClient(RuntimeResult(success=False, error_code="RUNTIME_UNAVAILABLE", error="missing jar"))
    manager = RuntimeProcessManager(client)

    status = manager.health()
    manager.close()

    assert status["state"] == "unavailable"
    assert status["error_code"] == "RUNTIME_UNAVAILABLE"
    assert client.closed is True
