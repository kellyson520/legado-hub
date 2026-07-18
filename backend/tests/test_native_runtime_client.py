import json
import sys

import pytest

from app.infrastructure.legado.engine.native_runtime_client import NativeRuntimeClient


@pytest.fixture
def fake_runtime_command(tmp_path):
    script = tmp_path / "fake_runtime.py"
    script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    print(json.dumps({'id': request['id'], 'protocol_version': 1, 'success': True, 'value': 'pong', 'value_type': 'string', 'trace': {'engine': 'fake'} }), flush=True)\n",
        encoding="utf-8",
    )
    return [sys.executable, "-u", str(script)]


def test_client_restarts_after_eof(fake_runtime_command):
    client = NativeRuntimeClient(command=fake_runtime_command)
    try:
        assert client.ping().success
        assert client._process is not None
        client._process.kill()
        assert client.ping().success
        assert client.restart_count == 1
    finally:
        client.close()


def test_client_rejects_mismatched_response_id(tmp_path):
    script = tmp_path / "bad_runtime.py"
    script.write_text(
        "import json, sys\n"
        "request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': 'wrong', 'success': True}), flush=True)\n",
        encoding="utf-8",
    )
    client = NativeRuntimeClient(command=[sys.executable, "-u", str(script)])
    try:
        result = client.ping()
        assert not result.success
        assert result.error_code == "MISMATCHED_RESPONSE_ID"
    finally:
        client.close()
