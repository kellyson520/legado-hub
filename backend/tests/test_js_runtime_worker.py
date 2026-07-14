import shutil
import time
import threading
from threading import Event, Thread

import pytest
from bs4 import BeautifulSoup

from app.infrastructure.legado.engine.js_runtime import JsRuntime
from app.infrastructure.legado.engine.js_session_models import JsExecutionContext
from app.infrastructure.legado.engine.js_session_models import JsExecutionTrace
from app.infrastructure.legado.engine.js_worker_bridge import JsWorkerClient


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required for worker tests")


def test_worker_client_executes_js_and_returns_cache_updates():
    client = JsWorkerClient()
    context = JsExecutionContext(
        stage="book_info_init",
        source={"bookSourceName": "测试源", "bookSourceUrl": "https://novel.cooks.tw"},
        result='{"data":{"articleid":362918,"name":"斗罗大陆"}}',
        base_url="https://novel.cooks.tw",
        cache={},
        variables={},
        headers={},
    )

    output = client.execute(
        code="result = JSON.parse(result); cache.putMemory('articleid', result.data.articleid); return result.data;",
        context=context,
    )

    assert output.success is True
    assert output.value["articleid"] == 362918
    assert output.cache_updates["articleid"] == 362918
    client.close()


class FakeWorkerClient:
    def execute(self, code, context):
        return type(
            "WorkerOutput",
            (),
            {
                "success": True,
                "value": {"articleid": 362918, "name": "斗罗大陆"},
                "cache_updates": {"articleid": 362918},
                "error_code": None,
                "error": None,
                "trace": JsExecutionTrace(stage=context.stage, success=True, rule_preview=code[:120]),
            },
        )()


def test_js_runtime_execute_with_metadata_keeps_legacy_execute_api():
    runtime = JsRuntime(worker_client=FakeWorkerClient())

    output = runtime.execute_with_metadata(
        "return {articleid: 362918, name: '斗罗大陆'};",
        data='{"data":{"articleid":362918}}',
        stage="book_info_init",
        source={"bookSourceName": "测试源", "bookSourceUrl": "https://novel.cooks.tw"},
        baseUrl="https://novel.cooks.tw",
    )

    assert output.success is True
    assert output.value["articleid"] == 362918
    assert runtime._cache["articleid"] == 362918
    assert output.trace.stage == "book_info_init"

    legacy = runtime.execute(
        "return {articleid: 362918, name: '斗罗大陆'};",
        data='{"data":{"articleid":362918}}',
        stage="book_info_init",
        source={"bookSourceName": "测试源", "bookSourceUrl": "https://novel.cooks.tw"},
        baseUrl="https://novel.cooks.tw",
    )
    assert legacy["name"] == "斗罗大陆"


def test_worker_client_serializes_html_tag_context_as_string():
    client = JsWorkerClient()
    tag = BeautifulSoup('<a href="/book-1">斗罗大陆</a>', "lxml").select_one("a")
    context = JsExecutionContext(
        stage="search_rule_js",
        source={"bookSourceName": "tag-test", "bookSourceUrl": "https://example.com"},
        result=tag,
        base_url="https://example.com",
        cache={},
        variables={},
        headers={},
    )

    output = client.execute(
        code="return result;",
        context=context,
    )

    assert output.success is True
    assert "斗罗大陆" in output.value
    client.close()


def test_worker_client_times_out_and_terminates_infinite_js_execution():
    client = JsWorkerClient(response_timeout_seconds=0.1)
    context = JsExecutionContext(
        stage="search_rule_js",
        source={},
        result={},
        base_url="",
        cache={},
        variables={},
        headers={},
    )
    started = time.monotonic()

    output = client.execute("while (true) {}", context)

    assert time.monotonic() - started < 1
    assert output.success is False
    assert output.error_code == "EXECUTION_TIMEOUT"
    assert client._process is None


def test_js_runtime_close_delegates_to_worker_client():
    class CloseableWorker:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    worker = CloseableWorker()
    runtime = JsRuntime(worker_client=worker)

    runtime.close()

    assert worker.close_calls == 1


def test_worker_client_returns_stable_failure_for_malformed_bridge_message(monkeypatch):
    import app.infrastructure.legado.engine.js_worker_bridge as bridge

    class FakeInput:
        def write(self, _value):
            return 0

        def flush(self):
            return None

    class FakeOutput:
        @staticmethod
        def fileno():
            return 99

    class FakeProcess:
        stdin = FakeInput()
        stdout = FakeOutput()

        def __init__(self):
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return self.returncode

    client = JsWorkerClient()
    client._process = FakeProcess()
    monkeypatch.setattr(bridge.select, 'select', lambda *_args: ([client._process.stdout], [], []))
    monkeypatch.setattr(bridge.os, 'read', lambda *_args: b'{"type":"bridge_http"}\n')
    context = JsExecutionContext(
        stage='search_rule_js', source={}, result={}, base_url='', cache={}, variables={}, headers={},
    )

    output = client.execute('return 1', context)

    assert output.success is False
    assert output.error_code == 'MALFORMED_RESPONSE'


def test_worker_client_times_out_when_worker_stalls_after_partial_line(tmp_path):
    worker = tmp_path / 'partial_worker.js'
    worker.write_text(
        "process.stdin.on('data', () => process.stdout.write('{\\\"success\\\":'));\n",
        encoding='utf-8',
    )
    client = JsWorkerClient(
        worker_path=worker,
        response_timeout_seconds=0.05,
        max_response_bytes=1024,
    )
    context = JsExecutionContext(
        stage='search_rule_js', source={}, result={}, base_url='', cache={}, variables={}, headers={},
    )
    outcome = {}
    finished = Event()

    def execute():
        try:
            outcome['output'] = client.execute('return 1', context)
        except Exception as error:
            outcome['error'] = error
        finally:
            finished.set()

    thread = Thread(target=execute)
    thread.start()
    thread.join(0.3)
    completed_without_forced_close = finished.is_set()
    if not completed_without_forced_close:
        client.close()
        thread.join(1)

    assert completed_without_forced_close is True
    assert outcome['output'].error_code == 'EXECUTION_TIMEOUT'
    assert client._process is None


def test_worker_client_rejects_oversized_response_before_json_parsing(tmp_path):
    worker = tmp_path / 'large_worker.js'
    worker.write_text(
        "process.stdin.on('data', () => process.stdout.write(JSON.stringify({success:true,value:'x'.repeat(4096)}) + '\\n'));\n",
        encoding='utf-8',
    )
    client = JsWorkerClient(
        worker_path=worker,
        response_timeout_seconds=0.5,
        max_response_bytes=128,
    )
    context = JsExecutionContext(
        stage='search_rule_js', source={}, result={}, base_url='', cache={}, variables={}, headers={},
    )

    output = client.execute('return 1', context)

    assert output.success is False
    assert output.error_code == 'RESPONSE_TOO_LARGE'
    assert client._process is None


def test_worker_client_times_out_slow_bridge_handler_within_response_deadline(tmp_path):
    worker = tmp_path / 'bridge_worker.js'
    worker.write_text(
        "process.stdin.on('data', () => process.stdout.write(JSON.stringify({type:'bridge_http',id:'bridge-1',request:{url:'https://example.test'}}) + '\\n'));\n",
        encoding='utf-8',
    )

    marker = tmp_path / 'bridge-called'

    def slow_bridge(_request):
        marker.write_text('called', encoding='utf-8')
        time.sleep(0.6)
        return {'status': 200, 'text': 'late', 'headers': {}}

    client = JsWorkerClient(
        worker_path=worker,
        bridge_http_handler=slow_bridge,
        response_timeout_seconds=0.3,
    )
    context = JsExecutionContext(
        stage='search_rule_js', source={}, result={}, base_url='', cache={}, variables={}, headers={},
    )
    started = time.monotonic()

    output = client.execute('return 1', context)

    assert time.monotonic() - started < 0.45
    assert marker.read_text(encoding='utf-8') == 'called'
    assert output.success is False
    assert output.error_code == 'EXECUTION_TIMEOUT'
    assert client._process is None


def test_bridge_capacity_failure_resets_worker_before_next_execution(tmp_path, monkeypatch):
    import app.infrastructure.legado.engine.js_worker_bridge as bridge

    worker = tmp_path / 'stateful_bridge_worker.js'
    worker.write_text(
        "const fs=require('fs'); const marker=__dirname+'/bridge-once';\n"
        "process.stdin.on('data', () => {\n"
        "  if (!fs.existsSync(marker)) { fs.writeFileSync(marker, '1');\n"
        "    process.stdout.write(JSON.stringify({type:'bridge_http',id:'bridge-1',request:{url:'https://example.test'}})+'\\n');\n"
        "  } else { process.stdout.write(JSON.stringify({success:true,value:'fresh'})+'\\n'); }\n"
        "});\n",
        encoding='utf-8',
    )
    monkeypatch.setattr(bridge, '_BRIDGE_CALLBACK_SLOTS', threading.BoundedSemaphore(0))
    client = JsWorkerClient(worker_path=worker, bridge_http_handler=lambda _request: {})
    context = JsExecutionContext(
        stage='search_rule_js', source={}, result={}, base_url='', cache={}, variables={}, headers={},
    )

    failed = client.execute('return 1', context)

    assert failed.success is False
    assert failed.error_code == 'BRIDGE_CAPACITY_EXHAUSTED'
    assert client._process is None

    recovered = client.execute('return 1', context)

    assert recovered.success is True
    assert recovered.value == 'fresh'


def test_worker_external_execution_deadline_preempts_infinite_execution():
    client = JsWorkerClient(response_timeout_seconds=0.5)
    client.set_execution_deadline(time.monotonic() + 0.05)
    context = JsExecutionContext(
        stage='search_rule_js', source={}, result={}, base_url='', cache={}, variables={}, headers={},
    )
    started = time.monotonic()

    output = client.execute('while (true) {}', context)

    assert time.monotonic() - started < 0.2
    assert output.success is False
    assert output.error_code == 'EXECUTION_TIMEOUT'
    assert client._process is None


def test_worker_expired_external_deadline_does_not_start_process():
    client = JsWorkerClient()
    client.set_execution_deadline(time.monotonic() - 1)
    context = JsExecutionContext(
        stage='search_rule_js', source={}, result={}, base_url='', cache={}, variables={}, headers={},
    )

    output = client.execute('return 1', context)

    assert output.success is False
    assert output.error_code == 'EXECUTION_TIMEOUT'
    assert client._process is None
