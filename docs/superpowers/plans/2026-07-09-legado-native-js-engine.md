# Legado Native JS Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the backend JS runtime so it reproduces Legado-native book-source JavaScript behavior as closely as possible, then add server-side observability, process control, and real-source regression coverage without breaking existing working sources.

**Architecture:** Add a native-semantics layer in Python, move complex JS execution to a long-lived Node worker, bridge `java.*` HTTP calls back into the existing `LegadoHttpClient`, and keep `RuleSelector` / `LegadoBookSourceFetcher` on a single execution-context contract. Treat compatibility as a first-class output by returning trace, cache updates, and compat diffs alongside raw JS values.

**Tech Stack:** Python 3.13, aiohttp, FastAPI, pytest, Node.js, `node:vm`, `cheerio`, BeautifulSoup, lxml, SQLite

---

> **Git note:** this working copy currently has no `.git`. Replace each “Commit” step with a filesystem checkpoint under `docs/superpowers/reports/checkpoints/`.

## File Structure

```text
backend/app/infrastructure/legado/engine/
├── js_session_models.py                 # shared dataclasses for JS execution context, trace, output, compat diff
├── legado_native_semantics.py           # native compatibility profile, stage context builder, diff helpers
├── js_worker_bridge.py                  # Node worker lifecycle, JSON-line protocol, bridge-call dispatch
├── js_runtime.py                        # runtime facade: builtin fast-path, worker execution, cache sync, legacy execute API
├── rule_selector.py                     # pass stage/context into @js: and inline JS execution
├── executor.py                          # use runtime metadata-capable execution path for js rules
├── http_client.py                       # unchanged HTTP transport reused by java.get/post/ajax bridge
└── __init__.py                          # export new compatibility/runtime symbols
backend/app/infrastructure/legado/
└── legado_fetcher.py                    # true @js: searchUrl execution, request-spec handling, per-stage context
backend/nodejs/
├── package.json                         # worker runtime dependency manifest (`cheerio` only)
├── legado_js_worker.js                  # long-lived worker entry, JSON-line protocol, vm sandbox
└── legado_shims/
    ├── native_env.js                    # inject java/cache/source/book/result/baseUrl globals
    └── jsoup.js                         # Jsoup-like parse/select/text/html/attr shim over cheerio
backend/scripts/
├── search_real_books.py                 # extend output with JS trace / compat summary
└── smoke_js_compat_sources.py           # real-source smoke focused on `@js:` and JS-heavy sources
backend/tests/
├── test_legado_native_semantics.py      # stage context, compat profile, diff generation
├── test_legado_compat_diff.py           # mismatch reporting
├── test_js_runtime_worker.py            # worker round-trip, cache sync, structured output
├── test_js_http_bridge.py               # java.get/post/ajax bridge behavior
├── test_jsoup_shim.py                   # Jsoup parse/select/text/html/attr compatibility
├── test_search_url_js_execution.py      # @js: searchUrl -> request spec -> search parse
└── test_legado_engine_compatibility.py  # keep legacy exports/compat cases green
```

### Task 1: Establish native semantics models and compatibility profile

**Files:**
- Create: `backend/app/infrastructure/legado/engine/js_session_models.py`
- Create: `backend/app/infrastructure/legado/engine/legado_native_semantics.py`
- Modify: `backend/app/infrastructure/legado/engine/__init__.py`
- Create: `backend/tests/test_legado_native_semantics.py`
- Create: `backend/tests/test_legado_compat_diff.py`

- [ ] **Step 1: Write the failing tests**

```python
from app.infrastructure.legado.engine.js_session_models import JsCompatDiff, JsExecutionTrace
from app.infrastructure.legado.engine.legado_native_semantics import LegadoJsCompatProfile


def test_native_profile_builds_stage_context_with_expected_variables():
    profile = LegadoJsCompatProfile.native_defaults()

    context = profile.build_context(
        stage="search_url_js",
        source={"bookSourceName": "测试源", "bookSourceUrl": "https://novel.cooks.tw"},
        book={"name": "斗罗大陆"},
        result=None,
        base_url="https://novel.cooks.tw",
        cache={"articleid": 362918},
        variables={"keyword": "斗罗大陆", "page": 1, "searchKey": "斗罗大陆"},
        headers={"User-Agent": "pytest-agent"},
    )

    assert context.stage == "search_url_js"
    assert context.source["bookSourceUrl"] == "https://novel.cooks.tw"
    assert context.variables["keyword"] == "斗罗大陆"
    assert context.cache["articleid"] == 362918
    assert context.headers["User-Agent"] == "pytest-agent"


def test_compat_diff_marks_native_mismatch_with_cache_keys():
    diff = JsCompatDiff.compare(
        expected_value={"url": "/search?wd=斗罗大陆"},
        actual_value={"url": "/search?wd=斗破苍穹"},
        expected_cache={"articleid": 362918},
        actual_cache={"articleid": 9527},
        trace=JsExecutionTrace(stage="search_url_js", success=False, rule_preview="return result"),
    )

    assert diff.code == "NATIVE_SEMANTICS_MISMATCH"
    assert "value" in diff.mismatch_fields
    assert "cache.articleid" in diff.mismatch_fields
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_legado_native_semantics.py tests\test_legado_compat_diff.py -v`  
Expected: FAIL because the new execution models, `LegadoJsCompatProfile`, and `JsCompatDiff.compare()` do not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/app/infrastructure/legado/engine/js_session_models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JsExecutionContext:
    stage: str
    source: dict[str, Any] = field(default_factory=dict)
    book: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    base_url: str = ""
    cache: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class JsExecutionTrace:
    stage: str
    success: bool
    rule_preview: str
    builtin_hit: bool = False
    worker_elapsed_ms: int = 0
    bridge_http_count: int = 0
    cache_keys_written: list[str] = field(default_factory=list)
    error_code: str | None = None


@dataclass
class JsCompatDiff:
    code: str
    mismatch_fields: list[str] = field(default_factory=list)
    expected_value: Any = None
    actual_value: Any = None
    expected_cache: dict[str, Any] = field(default_factory=dict)
    actual_cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def compare(cls, expected_value: Any, actual_value: Any, expected_cache: dict[str, Any], actual_cache: dict[str, Any], trace: JsExecutionTrace) -> "JsCompatDiff":
        mismatches: list[str] = []
        if expected_value != actual_value:
            mismatches.append("value")
        for key in sorted(set(expected_cache) | set(actual_cache)):
            if expected_cache.get(key) != actual_cache.get(key):
                mismatches.append(f"cache.{key}")
        code = "NATIVE_SEMANTICS_MISMATCH" if mismatches else "OK"
        return cls(code=code, mismatch_fields=mismatches, expected_value=expected_value, actual_value=actual_value, expected_cache=expected_cache, actual_cache=actual_cache)
```

```python
# backend/app/infrastructure/legado/engine/legado_native_semantics.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.legado.engine.js_session_models import JsExecutionContext


@dataclass
class LegadoJsCompatProfile:
    mode: str = "native"
    strict: bool = False
    allowed_stages: tuple[str, ...] = (
        "search_url_js",
        "search_rule_js",
        "book_info_init",
        "toc_rule_js",
        "content_rule_js",
    )
    default_variables: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def native_defaults(cls) -> "LegadoJsCompatProfile":
        return cls(
            mode="native",
            strict=False,
            default_variables={
                "page": 1,
                "keyword": "",
                "key": "",
                "searchKey": "",
            },
        )

    def build_context(self, stage: str, source: dict[str, Any] | None = None, book: dict[str, Any] | None = None, result: Any = None, base_url: str = "", cache: dict[str, Any] | None = None, variables: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> JsExecutionContext:
        if stage not in self.allowed_stages:
            raise ValueError(f"unsupported js stage: {stage}")
        merged_variables = dict(self.default_variables)
        merged_variables.update(variables or {})
        return JsExecutionContext(
            stage=stage,
            source=dict(source or {}),
            book=dict(book or {}),
            result=result,
            base_url=base_url,
            cache=dict(cache or {}),
            variables=merged_variables,
            headers=dict(headers or {}),
        )
```

```python
# backend/app/infrastructure/legado/engine/__init__.py
from app.infrastructure.legado.engine.js_session_models import JsCompatDiff, JsExecutionContext, JsExecutionTrace
from app.infrastructure.legado.engine.legado_native_semantics import LegadoJsCompatProfile

__all__ += [
    "JsExecutionContext",
    "JsExecutionTrace",
    "JsCompatDiff",
    "LegadoJsCompatProfile",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_legado_native_semantics.py tests\test_legado_compat_diff.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\infrastructure\legado\engine\legado_native_semantics.py docs\superpowers\reports\checkpoints\2026-07-09-js-engine-task1-legado-native-semantics.py`  
Expected: checkpoint file exists.

### Task 2: Build the long-lived Node worker bridge and protocol

**Files:**
- Create: `backend/app/infrastructure/legado/engine/js_worker_bridge.py`
- Create: `backend/nodejs/package.json`
- Create: `backend/nodejs/legado_js_worker.js`
- Create: `backend/nodejs/legado_shims/native_env.js`
- Create: `backend/tests/test_js_runtime_worker.py`

- [ ] **Step 1: Write the failing tests**

```python
import shutil

import pytest

from app.infrastructure.legado.engine.js_worker_bridge import JsWorkerClient
from app.infrastructure.legado.engine.js_session_models import JsExecutionContext


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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_js_runtime_worker.py -v`  
Expected: FAIL because `JsWorkerClient`, the Node worker script, and the worker protocol do not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/app/infrastructure/legado/engine/js_worker_bridge.py
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from app.infrastructure.legado.engine.js_session_models import JsExecutionContext, JsExecutionTrace


class JsWorkerOutput:
    def __init__(self, success: bool, value=None, cache_updates=None, error_code: str | None = None, error: str | None = None, trace: JsExecutionTrace | None = None):
        self.success = success
        self.value = value
        self.cache_updates = cache_updates or {}
        self.error_code = error_code
        self.error = error
        self.trace = trace or JsExecutionTrace(stage="unknown", success=success, rule_preview="")


class JsWorkerClient:
    def __init__(self, node_binary: str = "node", worker_path: Path | None = None):
        self._node_binary = node_binary
        self._worker_path = worker_path or Path(__file__).resolve().parents[4] / "nodejs" / "legado_js_worker.js"
        self._process: subprocess.Popen[str] | None = None

    def _ensure_started(self) -> None:
        if self._process and self._process.poll() is None:
            return
        self._process = subprocess.Popen(
            [self._node_binary, str(self._worker_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

    def execute(self, code: str, context: JsExecutionContext) -> JsWorkerOutput:
        self._ensure_started()
        started_at = time.time()
        payload = {
            "type": "execute",
            "code": code,
            "context": {
                "stage": context.stage,
                "source": context.source,
                "book": context.book,
                "result": context.result,
                "baseUrl": context.base_url,
                "cache": context.cache,
                "variables": context.variables,
                "headers": context.headers,
            },
        }
        assert self._process is not None and self._process.stdin and self._process.stdout
        self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._process.stdin.flush()
        raw = self._process.stdout.readline()
        message = json.loads(raw)
        elapsed_ms = int((time.time() - started_at) * 1000)
        trace = JsExecutionTrace(
            stage=context.stage,
            success=bool(message.get("success")),
            rule_preview=code[:120],
            worker_elapsed_ms=elapsed_ms,
            cache_keys_written=sorted((message.get("cache") or {}).keys()),
            error_code=message.get("error_code"),
        )
        return JsWorkerOutput(
            success=bool(message.get("success")),
            value=message.get("value"),
            cache_updates=message.get("cache") or {},
            error_code=message.get("error_code"),
            error=message.get("error"),
            trace=trace,
        )

    def close(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
```

```json
// backend/nodejs/package.json
{
  "name": "legado-js-worker",
  "private": true,
  "version": "1.0.0",
  "type": "commonjs",
  "dependencies": {
    "cheerio": "1.0.0"
  }
}
```

```javascript
// backend/nodejs/legado_js_worker.js
const readline = require('node:readline');
const vm = require('node:vm');
const { createNativeEnv } = require('./legado_shims/native_env');

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

rl.on('line', async (line) => {
  const message = JSON.parse(line);
  const env = createNativeEnv(message.context);
  const sandbox = vm.createContext(env);
  try {
    const wrapped = `(async function(){ ${message.code} })()`;
    const value = await vm.runInContext(wrapped, sandbox, { timeout: 5000 });
    process.stdout.write(JSON.stringify({ success: true, value, cache: env.cache._data }) + '\n');
  } catch (error) {
    process.stdout.write(JSON.stringify({ success: false, error_code: 'JS_RUNTIME_ERROR', error: error.message, cache: env.cache._data }) + '\n');
  }
});
```

```javascript
// backend/nodejs/legado_shims/native_env.js
function createNativeEnv(context) {
  const memory = { ...(context.cache || {}) };
  return {
    result: context.result,
    source: context.source || {},
    book: context.book || {},
    baseUrl: context.baseUrl || '',
    variables: context.variables || {},
    cache: {
      _data: memory,
      putMemory(key, value) { this._data[key] = value; },
      getFromMemory(key) { return this._data[key]; },
      put(key, value) { this._data[key] = value; },
      get(key) { return this._data[key]; },
    },
    java: {
      base64Encode(input) { return Buffer.from(String(input)).toString('base64'); },
      base64Decode(input) { return Buffer.from(String(input), 'base64').toString('utf8'); },
      md5Encode(input) { return require('node:crypto').createHash('md5').update(String(input)).digest('hex'); },
    },
    JSON,
    console,
  };
}

module.exports = { createNativeEnv };
```

- [ ] **Step 4: Install the worker dependency and run the test**

Run: `npm --prefix backend\nodejs install`  
Expected: installs `cheerio` and creates `backend\nodejs\package-lock.json`.

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_js_runtime_worker.py -v`  
Expected: PASS on machines with Node installed.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\infrastructure\legado\engine\js_worker_bridge.py docs\superpowers\reports\checkpoints\2026-07-09-js-engine-task2-worker-bridge.py`  
Expected: checkpoint file exists.

### Task 3: Refactor `JsRuntime` and `RuleSelector` around native semantics + structured output

**Files:**
- Modify: `backend/app/infrastructure/legado/engine/js_runtime.py`
- Modify: `backend/app/infrastructure/legado/engine/rule_selector.py`
- Modify: `backend/app/infrastructure/legado/engine/executor.py`
- Modify: `backend/app/infrastructure/legado/engine/__init__.py`
- Modify: `backend/tests/test_legado_engine_compatibility.py`
- Modify: `backend/tests/test_js_runtime_worker.py`

- [ ] **Step 1: Write the failing tests**

```python
from app.infrastructure.legado.engine.js_runtime import JsRuntime
from app.infrastructure.legado.engine.js_session_models import JsExecutionTrace


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
```

```python
from app.infrastructure.legado.engine.rule_selector import RuleSelector


def test_rule_selector_inline_js_passes_stage_context_into_runtime():
    class FakeRuntime:
        def __init__(self):
            self.received = None

        def execute(self, code, data=None, **kwargs):
            self.received = kwargs
            return "斗罗大陆"

    runtime = FakeRuntime()
    result = RuleSelector.extract(
        {"book": {"name": "ignored"}},
        "$.book@js: result.name",
        "https://novel.cooks.tw",
        False,
        context={"js_runtime": runtime, "stage": "search_rule_js"},
    )

    assert result.success is True
    assert result.value == "斗罗大陆"
    assert runtime.received["stage"] == "search_rule_js"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_js_runtime_worker.py tests\test_legado_engine_compatibility.py -v`  
Expected: FAIL because `execute_with_metadata()` does not exist and `RuleSelector` does not forward stage-aware context.

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/app/infrastructure/legado/engine/js_runtime.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.infrastructure.legado.engine.js_session_models import JsCompatDiff, JsExecutionTrace
from app.infrastructure.legado.engine.js_worker_bridge import JsWorkerClient
from app.infrastructure.legado.engine.legado_native_semantics import LegadoJsCompatProfile


@dataclass
class JsInvocationResult:
    success: bool
    value: Any = None
    error_code: str | None = None
    error: str | None = None
    trace: JsExecutionTrace | None = None
    cache_updates: dict[str, Any] | None = None
    compat_diff: JsCompatDiff | None = None


class JsRuntime:
    def __init__(self, worker_client: JsWorkerClient | None = None, compat_profile: LegadoJsCompatProfile | None = None):
        self._cache: dict[str, Any] = {}
        self._worker = worker_client or JsWorkerClient()
        self._compat_profile = compat_profile or LegadoJsCompatProfile.native_defaults()

    def execute_with_metadata(self, code: str, data: Any = None, **kwargs) -> JsInvocationResult:
        context = self._compat_profile.build_context(
            stage=kwargs.get("stage", "search_rule_js"),
            source=kwargs.get("source"),
            book=kwargs.get("book"),
            result=data,
            base_url=kwargs.get("baseUrl", ""),
            cache=self._cache,
            variables=kwargs.get("variables"),
            headers=kwargs.get("headers"),
        )
        builtin = self._try_builtin_patterns(code.strip(), {"result": data})
        if builtin is not None:
            trace = JsExecutionTrace(stage=context.stage, success=True, rule_preview=code[:120], builtin_hit=True)
            return JsInvocationResult(success=True, value=builtin, trace=trace, cache_updates={})

        worker_output = self._worker.execute(code, context)
        self._cache.update(worker_output.cache_updates)
        return JsInvocationResult(
            success=worker_output.success,
            value=worker_output.value,
            error_code=worker_output.error_code,
            error=worker_output.error,
            trace=worker_output.trace,
            cache_updates=worker_output.cache_updates,
        )

    def execute(self, code: str, data: Any = None, **kwargs) -> Any:
        output = self.execute_with_metadata(code, data=data, **kwargs)
        return output.value if output.success else None
```

```python
# backend/app/infrastructure/legado/engine/rule_selector.py
if rule_type == RuleType.JS:
    js_code = cls._strip_js_wrapper(base_rule)
    value = cls._get_js_runtime(context).execute(
        js_code,
        data,
        result=data,
        baseUrl=base_url,
        stage=context.get("stage", "search_rule_js"),
        **context,
    )
```

```python
# backend/app/infrastructure/legado/engine/executor.py
if rule.rule_type == "js":
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(rule.expression, sample, stage="executor_js_rule")
    if not output.success or output.value is None:
        return ExecutionResult(values=[], diagnostics=[output.error_code or output.error or "js runtime returned no value"])
    if isinstance(output.value, list):
        return ExecutionResult(values=[str(item) for item in output.value], diagnostics=[])
    return ExecutionResult(values=[str(output.value)], diagnostics=[])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_js_runtime_worker.py tests\test_legado_engine_compatibility.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\infrastructure\legado\engine\js_runtime.py docs\superpowers\reports\checkpoints\2026-07-09-js-engine-task3-js-runtime.py`  
Expected: checkpoint file exists.

### Task 4: Wire `LegadoBookSourceFetcher` for true `@js:` searchUrl and HTTP bridge calls

**Files:**
- Modify: `backend/app/infrastructure/legado/legado_fetcher.py`
- Modify: `backend/app/infrastructure/legado/engine/js_worker_bridge.py`
- Modify: `backend/nodejs/legado_shims/native_env.js`
- Create: `backend/tests/test_js_http_bridge.py`
- Create: `backend/tests/test_search_url_js_execution.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from app.infrastructure.legado.engine.http_client import HttpResponse
from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def execute_with_metadata(self, code, data=None, **kwargs):
        self.calls.append(kwargs)
        return type(
            "RuntimeOutput",
            (),
            {
                "success": True,
                "value": {
                    "request": {
                        "url": "https://a.example.com/search?wd=斗罗大陆",
                        "method": "GET",
                        "headers": {"X-Test": "1"},
                    }
                },
                "error_code": None,
                "error": None,
                "trace": None,
                "cache_updates": {},
                "compat_diff": None,
            },
        )()


class FakeHttpClient:
    async def get(self, url, headers=None, **kwargs):
        assert url == "https://a.example.com/search?wd=斗罗大陆"
        assert headers["X-Test"] == "1"
        return HttpResponse(
            url=url,
            status=200,
            text='<div class="book"><a class="title" href="/book-1">斗罗大陆</a><span class="author">唐家三少</span></div>',
            is_html=True,
        )


@pytest.mark.asyncio
async def test_fetcher_executes_js_search_url_and_parses_results():
    fetcher = LegadoBookSourceFetcher()
    fetcher._js_runtime = FakeRuntime()
    fetcher._http = FakeHttpClient()

    source = {
        "bookSourceName": "JS搜索源",
        "bookSourceUrl": "https://a.example.com",
        "searchUrl": "@js: return {request: {url: baseUrl + '/search?wd=' + variables.keyword, method: 'GET', headers: {'X-Test': '1'}}};",
        "ruleSearch": {
            "bookList": ".book",
            "name": ".title@text",
            "author": ".author@text",
            "bookUrl": ".title@href",
        },
    }

    books = await fetcher.search(source, "斗罗大陆")

    assert books[0]["name"] == "斗罗大陆"
    assert books[0]["author"] == "唐家三少"
    assert books[0]["bookUrl"] == "https://a.example.com/book-1"
    assert fetcher._js_runtime.calls[0]["stage"] == "search_url_js"
```

```python
import shutil

import pytest

from app.infrastructure.legado.engine.js_runtime import JsRuntime


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required for bridge tests")


def test_js_runtime_java_get_bridge_reads_remote_payload():
    class BridgeRuntime(JsRuntime):
        def _handle_bridge_http(self, request_spec):
            assert request_spec["url"] == "https://api.example.com/search?wd=斗罗大陆"
            return {"status": 200, "text": '{"items":[{"name":"斗罗大陆"}]}'}

    runtime = BridgeRuntime()
    output = runtime.execute_with_metadata(
        "return JSON.parse(await java.get('https://api.example.com/search?wd=斗罗大陆')).items[0].name;",
        stage="search_url_js",
        source={"bookSourceName": "bridge-test", "bookSourceUrl": "https://api.example.com"},
        baseUrl="https://api.example.com",
    )

    assert output.success is True
    assert output.value == "斗罗大陆"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_search_url_js_execution.py tests\test_js_http_bridge.py -v`  
Expected: FAIL because `searchUrl` still skips pure `@js:` and the worker/runtime do not support bridge-backed `java.get`.

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/app/infrastructure/legado/legado_fetcher.py
async def search(self, source: dict[str, Any], keyword: str, page: int = 1) -> list[dict[str, Any]]:
    search_url_tmpl = source.get("searchUrl", "")
    if not search_url_tmpl:
        return []

    base_url = UrlUtils.get_base_url(source.get("bookSourceUrl", ""))
    variables = {
        "keyword": keyword,
        "key": quote(keyword),
        "searchKey": quote(keyword),
        "page": page,
    }
    headers = UrlUtils.parse_headers(source.get("header", ""))

    if search_url_tmpl.strip().startswith("@js:"):
        output = self._js_runtime.execute_with_metadata(
            search_url_tmpl.strip()[4:].strip(),
            data=None,
            stage="search_url_js",
            source=source,
            baseUrl=base_url,
            variables=variables,
            headers=headers,
        )
        if not output.success:
            return []
        request_spec = output.value.get("request") if isinstance(output.value, dict) else None
        response_data = output.value.get("response") if isinstance(output.value, dict) else None
        if request_spec:
            method = str(request_spec.get("method", "GET")).upper()
            merged_headers = {**headers, **(request_spec.get("headers") or {})}
            if method == "POST":
                resp = await self._http.post(request_spec["url"], data=request_spec.get("body"), headers=merged_headers)
            else:
                resp = await self._http.get(request_spec["url"], headers=merged_headers)
            resp_data = self._extract_response_data(resp)
            is_html = resp.is_html
        else:
            resp_data = response_data
            is_html = isinstance(resp_data, str)
    else:
        url_tmpl, method, body_tmpl = UrlUtils.parse_search_url(search_url_tmpl)
        search_url = UrlUtils.fill_template(url_tmpl, variables, encode=False)
        if not search_url.startswith("http"):
            search_url = UrlUtils.resolve_relative(search_url, base_url)
        if method == "POST":
            body_data = UrlUtils.fill_template(body_tmpl or "", variables, encode=False)
            resp = await self._http.post(search_url, data=body_data, headers=headers)
        else:
            resp = await self._http.get(search_url, headers=headers)
        resp_data = self._extract_response_data(resp)
        is_html = resp.is_html
```

```python
# backend/app/infrastructure/legado/engine/js_worker_bridge.py
class JsWorkerClient:
    def __init__(self, node_binary: str = "node", worker_path: Path | None = None, bridge_http_handler=None):
        self._node_binary = node_binary
        self._worker_path = worker_path or Path(__file__).resolve().parents[4] / "nodejs" / "legado_js_worker.js"
        self._bridge_http_handler = bridge_http_handler
        self._process: subprocess.Popen[str] | None = None

    def execute(self, code: str, context: JsExecutionContext) -> JsWorkerOutput:
        self._ensure_started()
        payload = {
            "type": "execute",
            "code": code,
            "context": {
                "stage": context.stage,
                "source": context.source,
                "book": context.book,
                "result": context.result,
                "baseUrl": context.base_url,
                "cache": context.cache,
                "variables": context.variables,
                "headers": context.headers,
            },
        }
        assert self._process is not None and self._process.stdin and self._process.stdout
        self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._process.stdin.flush()
        while True:
            raw = self._process.stdout.readline()
            message = json.loads(raw)
            if message.get("type") == "bridge_http":
                response = self._bridge_http_handler(message["request"]) if self._bridge_http_handler else {"status": 500, "text": "bridge handler missing"}
                self._process.stdin.write(json.dumps({"type": "bridge_http_result", "id": message["id"], "response": response}, ensure_ascii=False) + "\n")
                self._process.stdin.flush()
                continue
            return JsWorkerOutput(
                success=bool(message.get("success")),
                value=message.get("value"),
                cache_updates=message.get("cache") or {},
                error_code=message.get("error_code"),
                error=message.get("error"),
                trace=JsExecutionTrace(stage=context.stage, success=bool(message.get("success")), rule_preview=code[:120], bridge_http_count=int(message.get("bridge_http_count", 0))),
            )
```

```javascript
// backend/nodejs/legado_shims/native_env.js
function createBridgeJava(sendBridgeHttp, memory) {
  return {
    async get(url, headers = {}) {
      const response = await sendBridgeHttp({ method: 'GET', url, headers });
      return response.text;
    },
    async post(url, body = '', headers = {}) {
      const response = await sendBridgeHttp({ method: 'POST', url, body, headers });
      return response.text;
    },
    async ajax(config) {
      const normalized = typeof config === 'string' ? { method: 'GET', url: config } : config;
      const response = await sendBridgeHttp(normalized);
      return response.text;
    },
    base64Encode(input) { return Buffer.from(String(input)).toString('base64'); },
    base64Decode(input) { return Buffer.from(String(input), 'base64').toString('utf8'); },
    md5Encode(input) { return require('node:crypto').createHash('md5').update(String(input)).digest('hex'); },
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_search_url_js_execution.py tests\test_js_http_bridge.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\infrastructure\legado\legado_fetcher.py docs\superpowers\reports\checkpoints\2026-07-09-js-engine-task4-fetcher-js-search.py`  
Expected: checkpoint file exists.

### Task 5: Add Jsoup shim, compat-diff reporting, and real-source JS regression scripts

**Files:**
- Create: `backend/nodejs/legado_shims/jsoup.js`
- Modify: `backend/nodejs/legado_shims/native_env.js`
- Modify: `backend/app/infrastructure/legado/engine/js_runtime.py`
- Create: `backend/tests/test_jsoup_shim.py`
- Modify: `backend/tests/test_legado_compat_diff.py`
- Modify: `backend/scripts/search_real_books.py`
- Create: `backend/scripts/smoke_js_compat_sources.py`

- [ ] **Step 1: Write the failing tests**

```python
import shutil

import pytest

from app.infrastructure.legado.engine.js_runtime import JsRuntime


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required for jsoup tests")


def test_jsoup_parse_select_text_html_and_attr():
    runtime = JsRuntime()
    output = runtime.execute_with_metadata(
        """
        var doc = org.jsoup.Jsoup.parse(result);
        return {
          title: doc.select('.title').text(),
          href: doc.select('a.title').attr('href'),
          html: doc.select('#intro').html()
        };
        """,
        data='<div><a class="title" href="/book-1">斗罗大陆</a><div id="intro"><p>第一部</p></div></div>',
        stage="content_rule_js",
        source={"bookSourceName": "jsoup-test", "bookSourceUrl": "https://a.example.com"},
        baseUrl="https://a.example.com",
    )

    assert output.success is True
    assert output.value["title"] == "斗罗大陆"
    assert output.value["href"] == "/book-1"
    assert "第一部" in output.value["html"]
```

```python
from app.infrastructure.legado.engine.js_session_models import JsCompatDiff, JsExecutionTrace


def test_compat_diff_reports_no_mismatch_when_values_and_cache_match():
    diff = JsCompatDiff.compare(
        expected_value={"title": "斗罗大陆"},
        actual_value={"title": "斗罗大陆"},
        expected_cache={"articleid": 362918},
        actual_cache={"articleid": 362918},
        trace=JsExecutionTrace(stage="content_rule_js", success=True, rule_preview="doc.select('.title').text()"),
    )

    assert diff.code == "OK"
    assert diff.mismatch_fields == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_jsoup_shim.py tests\test_legado_compat_diff.py -v`  
Expected: FAIL because `org.jsoup.Jsoup.parse` is not implemented and `JsCompatDiff` does not yet participate in real runtime output.

- [ ] **Step 3: Write the minimal implementation**

```javascript
// backend/nodejs/legado_shims/jsoup.js
const cheerio = require('cheerio');

function wrapSelection(selection) {
  return {
    text() { return selection.text(); },
    html() { return selection.html() || ''; },
    attr(name) { return selection.attr(name) || ''; },
    get(index) { return wrapSelection(selection.eq(index)); },
    size() { return selection.length; },
    first() { return wrapSelection(selection.first()); },
    eq(index) { return wrapSelection(selection.eq(index)); },
    select(selector) { return wrapSelection(selection.find(selector)); },
  };
}

function createJsoup() {
  return {
    parse(html) {
      const $ = cheerio.load(String(html || ''));
      return {
        select(selector) {
          return wrapSelection($(selector));
        },
        text() {
          return $.root().text();
        },
        html() {
          return $.root().html() || '';
        },
      };
    },
  };
}

module.exports = { createJsoup };
```

```javascript
// backend/nodejs/legado_shims/native_env.js
const { createJsoup } = require('./jsoup');

function createNativeEnv(context, sendBridgeHttp) {
  const memory = { ...(context.cache || {}) };
  return {
    result: context.result,
    source: context.source || {},
    book: context.book || {},
    baseUrl: context.baseUrl || '',
    variables: context.variables || {},
    cache: {
      _data: memory,
      putMemory(key, value) { this._data[key] = value; },
      getFromMemory(key) { return this._data[key]; },
      put(key, value) { this._data[key] = value; },
      get(key) { return this._data[key]; },
    },
    java: createBridgeJava(sendBridgeHttp, memory),
    org: { jsoup: { Jsoup: createJsoup() } },
    JSON,
    console,
  };
}
```

```python
# backend/app/infrastructure/legado/engine/js_runtime.py
def execute_with_metadata(self, code: str, data: Any = None, expected_value: Any = None, expected_cache: dict[str, Any] | None = None, **kwargs) -> JsInvocationResult:
    context = self._compat_profile.build_context(
        stage=kwargs.get("stage", "search_rule_js"),
        source=kwargs.get("source"),
        book=kwargs.get("book"),
        result=data,
        base_url=kwargs.get("baseUrl", ""),
        cache=self._cache,
        variables=kwargs.get("variables"),
        headers=kwargs.get("headers"),
    )
    worker_output = self._worker.execute(code, context)
    self._cache.update(worker_output.cache_updates)
    compat_diff = None
    if expected_value is not None or expected_cache is not None:
        compat_diff = JsCompatDiff.compare(
            expected_value=expected_value,
            actual_value=worker_output.value,
            expected_cache=expected_cache or {},
            actual_cache=self._cache,
            trace=worker_output.trace,
        )
    return JsInvocationResult(
        success=worker_output.success,
        value=worker_output.value,
        error_code=worker_output.error_code,
        error=worker_output.error,
        trace=worker_output.trace,
        cache_updates=worker_output.cache_updates,
        compat_diff=compat_diff,
    )
```

```python
# backend/scripts/smoke_js_compat_sources.py
from pathlib import Path
import asyncio
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-32-bytes-minimum")

from app.infrastructure.persistence.factory import build_source_read_service

DEFAULT_KEYWORDS = ["捞尸人", "斗罗大陆"]


async def main():
    service = build_source_read_service()
    try:
        sources = await service._repo.list_book_sources_full(enabled_only=True)
        js_sources = [item for item in sources if str(item.get("searchUrl", "")).strip().startswith("@js:")][:10]
        print(f"[js-compat] selected_sources={len(js_sources)}")
        for source in js_sources:
            for keyword in DEFAULT_KEYWORDS:
                result = await service.search_books(keyword=keyword, source_ids=[source["id"]], limit_per_source=1)
                print(f"[js-compat] source_id={source['id']} keyword={keyword} hits={len(result['items'])}")
    finally:
        await service._fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run the tests and the real-source JS smoke**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_jsoup_shim.py tests\test_legado_compat_diff.py tests\test_js_runtime_worker.py tests\test_js_http_bridge.py tests\test_search_url_js_execution.py tests\test_legado_engine_compatibility.py -v`  
Expected: PASS.

Run: `.\.venv\Scripts\python.exe scripts\search_real_books.py`  
Expected: still prints successful hits for existing sources (`7`, `12`, `33`) and now includes JS trace / compat summary lines without regressing current success cases.

Run: `.\.venv\Scripts\python.exe scripts\smoke_js_compat_sources.py`  
Expected: prints at least a small set of `@js:` sources and shows per-keyword hit counts instead of silently skipping them.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\scripts\smoke_js_compat_sources.py docs\superpowers\reports\checkpoints\2026-07-09-js-engine-task5-js-compat-smoke.py`  
Expected: checkpoint file exists.

## Self-review

### Spec coverage

- Native-semantics layer and compatibility baseline: covered by Task 1.
- Long-lived Node worker and protocol: covered by Task 2.
- Runtime refactor with structured output and legacy API preservation: covered by Task 3.
- Pure `@js:` `searchUrl` execution and `java.get/post/ajax` HTTP bridge: covered by Task 4.
- Jsoup compatibility, compat diff reporting, and real-source JS smoke: covered by Task 5.
- Existing working sources must not regress: verified in Task 5 by rerunning `scripts\search_real_books.py` plus compatibility-focused tests.

### Placeholder scan

- No unresolved placeholder markers remain.
- Every task includes exact file paths, concrete tests, exact commands, and a filesystem checkpoint.
- The plan avoids Git-only actions because this workspace has no `.git`.

### Type consistency

- `JsExecutionContext`, `JsExecutionTrace`, and `JsCompatDiff` are introduced in Task 1 and reused consistently in Tasks 2–5.
- `JsRuntime.execute_with_metadata()` is the metadata-capable API; `execute()` remains the legacy value-only wrapper.
- `LegadoJsCompatProfile.build_context()` is the only context-construction path used by the runtime.
- `JsWorkerClient.execute()` returns worker output consumed by `JsRuntime`, `LegadoBookSourceFetcher`, and compatibility tests with the same field names: `success`, `value`, `cache_updates`, `error_code`, `error`, `trace`.

Plan complete and saved to `docs/superpowers/plans/2026-07-09-legado-native-js-engine.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
