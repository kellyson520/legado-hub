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


def test_client_restarts_when_runtime_closes_stdout_before_exit(tmp_path):
    script = tmp_path / "eof_runtime.py"
    marker = tmp_path / "ready"
    script.write_text(
        "import json, os, pathlib, sys, time\n"
        "marker = pathlib.Path(sys.argv[1])\n"
        "if not marker.exists():\n"
        "    marker.touch()\n"
        "    os.close(1)\n"
        "    time.sleep(2)\n"
        "else:\n"
        "    for line in sys.stdin:\n"
        "        request = json.loads(line)\n"
        "        print(json.dumps({'id': request['id'], 'success': True, 'value': 'pong', 'value_type': 'string'}), flush=True)\n",
        encoding="utf-8",
    )
    client = NativeRuntimeClient(
        command=[sys.executable, "-u", str(script), str(marker)],
        response_timeout=0.5,
    )
    try:
        result = client.ping()
        assert result.success
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


def test_client_answers_bridge_cache_messages(tmp_path):
    script = tmp_path / "cache_runtime.py"
    script.write_text(
        "import json, sys\n"
        "request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'type': 'bridge_cache', 'id': 'cache-1', 'request': {'op': 'get', 'scope': 'source-a', 'key': 'token'}}), flush=True)\n"
        "bridge = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': request['id'], 'success': True, 'value': bridge['response']['value'], 'value_type': 'string'}), flush=True)\n",
        encoding="utf-8",
    )
    calls = []

    def cache_handler(request):
        calls.append(request)
        return {"found": True, "value": "cache-ok"}

    client = NativeRuntimeClient(
        command=[sys.executable, "-u", str(script)],
        cache_handler=cache_handler,
    )
    try:
        result = client.call("extract_string", {}, timeout=1.0)
        assert result.success
        assert result.value == "cache-ok"
        assert calls == [{"op": "get", "scope": "source-a", "key": "token"}]
    finally:
        client.close()


def test_stderr_drain_treats_closed_stream_as_normal_shutdown():
    class ClosedStream:
        def readline(self):
            raise ValueError("I/O operation on closed file")

    class Process:
        stderr = ClosedStream()

    client = NativeRuntimeClient(command=[sys.executable])
    client._drain_stderr(Process())
    assert list(client._stderr_lines) == []
