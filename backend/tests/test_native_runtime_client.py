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


def test_client_reports_unavailable_when_process_cannot_start():
    client = NativeRuntimeClient(command=["/definitely/missing/legado-runtime"])
    result = client.ping()
    assert not result.success
    assert result.error_code == "RUNTIME_UNAVAILABLE"


def test_client_answers_bridge_http_messages(tmp_path):
    script = tmp_path / "bridge_runtime.py"
    script.write_text(
        "import json, sys\n"
        "request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'type': 'bridge_http', 'id': 'bridge-1', 'request': {'url': 'https://example.test', 'method': 'GET'}}), flush=True)\n"
        "bridge = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': request['id'], 'success': True, 'value': bridge['response']['text'], 'value_type': 'string'}), flush=True)\n",
        encoding="utf-8",
    )
    calls = []

    def bridge_handler(request):
        calls.append(request)
        return {"status": 200, "text": "bridge-ok", "headers": {}}

    client = NativeRuntimeClient(command=[sys.executable, "-u", str(script)], bridge_handler=bridge_handler)
    try:
        result = client.call("extract_string", {}, timeout=1.0)
        assert result.success
        assert result.value == "bridge-ok"
        assert calls == [{"url": "https://example.test", "method": "GET"}]
    finally:
        client.close()
