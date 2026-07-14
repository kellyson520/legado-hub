import shutil
import time

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
        def readline(self):
            return '{"type":"bridge_http"}\n'

    class FakeProcess:
        stdin = FakeInput()
        stdout = FakeOutput()

        @staticmethod
        def poll():
            return None

    client = JsWorkerClient()
    client._process = FakeProcess()
    monkeypatch.setattr(bridge.select, 'select', lambda *_args: ([client._process.stdout], [], []))
    context = JsExecutionContext(
        stage='search_rule_js', source={}, result={}, base_url='', cache={}, variables={}, headers={},
    )

    output = client.execute('return 1', context)

    assert output.success is False
    assert output.error_code == 'MALFORMED_RESPONSE'
