import sys

from app.infrastructure.legado.engine.native_models import RuntimeResult
from app.infrastructure.legado.engine.native_runtime_client import NativeRuntimeClient
from app.infrastructure.legado.engine.runtime_facade import LegadoRuntimeFacade


def test_runtime_client_timeout_restarts_process(tmp_path):
    script = tmp_path / "slow_runtime.py"
    script.write_text(
        "import time\n"
        "time.sleep(5)\n",
        encoding="utf-8",
    )
    client = NativeRuntimeClient(command=[sys.executable, "-u", str(script)], response_timeout=0.01)

    result = client.ping()

    assert not result.success
    assert result.error_code == "EXECUTION_TIMEOUT"
    assert client.restart_count == 1
    client.close()


def test_facade_marks_fallback_reason_without_hiding_native_error():
    class FailedClient:
        def call(self, operation, payload, timeout):
            return RuntimeResult(success=False, error_code="WORKER_EOF", error="worker stopped")

    class Fallback:
        def extract(self, *args, **kwargs):
            return RuntimeResult(success=True, value="fallback", value_type="string")

    result = LegadoRuntimeFacade(
        native_client=FailedClient(),
        fallback=Fallback(),
        mode="native_kotlin",
    ).extract("<div>ok</div>", "div@text")

    assert result.success
    assert result.value == "fallback"
    assert result.trace["fallback_reason"] == "WORKER_EOF"
