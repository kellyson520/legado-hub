# Legado Native Kotlin Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在单个 Docker 容器内接入与官方 Legado 语义一致的 Kotlin 解析内核，并通过稳定的 Python Facade 逐步迁移现有书源、Agent 和健康探针流程。

**Architecture:** 从 `HapeLee/legado-with-MD3` 锁定 commit 抽取 Android 无关的解析核心，编译为 headless JVM fat JAR。FastAPI 通过本地 stdio JSON-RPC 调用该 JAR；Python 继续负责 HTTP、Cookie、缓存、审计和业务编排，旧 Python/Node 引擎只作为有原因的回退。所有业务代码只依赖 `LegadoRuntimeFacade`。

**Tech Stack:** Kotlin/JVM 17、Gradle、Jsoup、JsoupXpath、Jayway JsonPath、Rhino、Gson、Python 3.11、FastAPI、pytest、Node.js worker、Docker multi-stage build、tini。

---

## 文件边界

先按下列边界创建文件，避免把 Android UI 或业务逻辑带入后端：

| 文件/目录 | 责任 |
|---|---|
| `runtime/legado-kotlin/` | headless Kotlin 工程、上游解析源码、端口适配和 stdio server |
| `runtime/legado-kotlin/vendor/` | GPL-3.0 上游源码快照，只放解析相关文件和版权头 |
| `runtime/legado-kotlin/src/main/kotlin/.../headless/` | HTTP、Cookie、Cache、Scope、日志和取消端口 |
| `runtime/legado-kotlin/src/main/kotlin/.../protocol/` | JSON-RPC 请求、响应、错误和 framing |
| `backend/app/infrastructure/legado/engine/native_models.py` | Python 侧协议模型、trace 和错误类型 |
| `backend/app/infrastructure/legado/engine/native_runtime_client.py` | JVM 子进程生命周期、stdio I/O、超时和重启 |
| `backend/app/infrastructure/legado/engine/runtime_facade.py` | 业务唯一入口、能力路由、回退和 shadow diff |
| `backend/app/infrastructure/legado/engine/runtime_bridge.py` | Kotlin 到 Python 的 HTTP/缓存桥接 |
| `backend/tests/test_native_runtime_*.py` | Python 协议、进程和 Facade 契约测试 |
| `runtime/legado-kotlin/src/test/` | Kotlin 规则、协议和端口单元测试 |
| `backend/tests/fixtures/legado_runtime/` | HTML、JSON、规则和预期结果黄金语料 |
| `backend/scripts/run_legado_diff.py` | 批量运行 Kotlin/Python 差异对照 |
| `backend/Dockerfile` | JDK 构建阶段、JRE 运行阶段、tini 和 runtime JAR |
| `LICENSE`、`THIRD_PARTY_NOTICES.md` | GPL-3.0 和上游版权/修改说明 |

### Task 1: 补齐许可证和 headless 工程骨架

**Files:**
- Create: `LICENSE`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `runtime/legado-kotlin/settings.gradle.kts`
- Create: `runtime/legado-kotlin/build.gradle.kts`
- Create: `runtime/legado-kotlin/gradle.properties`
- Create: `runtime/legado-kotlin/gradlew`
- Create: `runtime/legado-kotlin/gradle/wrapper/gradle-wrapper.jar`
- Create: `runtime/legado-kotlin/gradle/wrapper/gradle-wrapper.properties`
- Create: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/Main.kt`
- Create: `runtime/legado-kotlin/src/test/kotlin/io/legado/headless/BuildSmokeTest.kt`

- [ ] **Step 1: 写许可证契约测试和上游说明**

  在 `backend/tests/test_license_metadata.py` 写测试，确保根目录存在 GPL-3.0、上游 commit 和修改说明：

  ```python
  import sys
  import pytest
  from app.infrastructure.legado.engine.native_models import RuntimeResult
  from app.infrastructure.legado.engine.http_client import HttpResponse

  from pathlib import Path

  ROOT = Path(__file__).parents[2]

  def test_gpl_and_upstream_notice_are_present():
      license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
      notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
      assert "GNU GENERAL PUBLIC LICENSE" in license_text
      assert "GPL-3.0" in notice
      assert "2c340d48bb1b9537690ec31eb9c23a57307f30a3" in notice
  ```

- [ ] **Step 2: 运行测试确认失败**

  Run: `cd backend && pytest tests/test_license_metadata.py -q`

  Expected: FAIL because `LICENSE` and `THIRD_PARTY_NOTICES.md` do not exist.

- [ ] **Step 3: 添加许可证和工程骨架**

  使用参考仓库的 LICENSE 原文作为根目录 LICENSE；创建 `THIRD_PARTY_NOTICES.md`，明确上游 URL、commit、GPL-3.0、复用文件范围和平台修改方式。`settings.gradle.kts` 和 `build.gradle.kts` 使用 Kotlin JVM 2.4.0、Gson 2.14.0、Jsoup 1.16.2、JsoupXpath 2.5.5、JsonPath 3.0.0、Rhino 1.8.1 依赖，并将入口指向 `io.legado.headless.MainKt`。从 Gradle 8.10 生成并提交 wrapper，确保 Docker 和本机使用同一构建版本。

  `Main.kt` 先只实现可执行的 `--version` 和 stdin echo：

  ```kotlin
  package io.legado.headless

  fun main(args: Array<String>) {
      if (args.contains("--version")) {
          println("legado-runtime protocol=1 engine=2c340d48bb1b9537690ec31eb9c23a57307f30a3")
          return
      }
      generateSequence(::readLine).forEach { println(it) }
  }
  ```

- [ ] **Step 4: 运行许可证和 JVM smoke 测试**

  Run: `cd backend && pytest tests/test_license_metadata.py -q`

  Run: `cd runtime/legado-kotlin && ./gradlew test`（若本机没有 Gradle，使用后续 Docker builder 执行同一命令）。

  Expected: Python license test PASS；Kotlin `BuildSmokeTest` PASS。

- [ ] **Step 5: 提交**

  ```bash
  git add LICENSE THIRD_PARTY_NOTICES.md runtime/legado-kotlin backend/tests/test_license_metadata.py
  git commit -m "build: add licensed legado headless runtime scaffold"
  ```

### Task 2: 抽取上游解析核心并定义 headless 端口

**Files:**
- Create: `runtime/legado-kotlin/vendor/io/legado/app/model/analyzeRule/AnalyzeRule.kt`
- Create: `runtime/legado-kotlin/vendor/io/legado/app/model/analyzeRule/AnalyzeByJSonPath.kt`
- Create: `runtime/legado-kotlin/vendor/io/legado/app/model/analyzeRule/AnalyzeByJSoup.kt`
- Create: `runtime/legado-kotlin/vendor/io/legado/app/model/analyzeRule/AnalyzeByXPath.kt`
- Create: `runtime/legado-kotlin/vendor/io/legado/app/model/analyzeRule/AnalyzeByRegex.kt`
- Create: `runtime/legado-kotlin/vendor/io/legado/app/model/analyzeRule/RuleAnalyzer.kt`
- Create: `runtime/legado-kotlin/vendor/io/legado/app/model/analyzeRule/RuleData.kt`
- Create: `runtime/legado-kotlin/vendor/io/legado/app/model/analyzeRule/RuleDataInterface.kt`
- Create: `runtime/legado-kotlin/vendor/io/legado/app/model/analyzeRule/CustomUrl.kt`
- Create: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/ports/HttpBridge.kt`
- Create: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/ports/CacheBridge.kt`
- Create: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/ports/SourceContext.kt`
- Create: `runtime/legado-kotlin/src/test/kotlin/io/legado/headless/NativeRuleSemanticsTest.kt`

- [ ] **Step 1: 写原生规则语义失败测试**

  覆盖规则链、`@CSS:`, 负索引、`&&/||/%%`、JSONPath 内嵌规则和 HTML `textNodes`：

  ```kotlin
  @Test fun css_negative_index_and_text_nodes_match_legado() {
      val html = "<ul><li>A</li><li>B</li><li>C</li></ul>"
      val analyzer = AnalyzeRule().setContent(html, "https://example.test/")
      assertEquals("C", analyzer.getString("ul@li.-1@text"))
      assertEquals(listOf("A", "B", "C"), analyzer.getStringList("ul@li@text"))
  }

  @Test fun json_inner_rules_and_fallback_are_preserved() {
      val json = "{\"items\":[{\"name\":\"A\"}]}"
      val analyzer = AnalyzeRule().setContent(json)
      assertEquals("A", analyzer.getString("$.items[0].name||$.missing"))
  }
  ```

- [ ] **Step 2: 运行测试确认缺少 vendor 实现**

  Run: `cd runtime/legado-kotlin && ./gradlew test --tests '*NativeRuleSemanticsTest'`

  Expected: FAIL because the upstream classes and Android-independent adapters have not been added.

- [ ] **Step 3: 复制并登记上游解析文件**

  从 `/tmp/legado-with-MD3` 的锁定 commit 复制上述文件，保留文件头和 GPL-3.0 声明；不要复制 Android UI、Room、Activity、WebView 或整个 `AnalyzeUrl.kt` 的 Android 业务依赖。把 `AnalyzeRule` 依赖的 `BaseSource`、`BaseBook`、`BookChapter`、`RssArticle`、`CacheManager`、`CookieStore` 和 `JsExtensions` 替换为 `SourceContext`、`CacheBridge` 和 `HttpBridge` 端口。

  端口接口固定为：

  ```kotlin
  interface HttpBridge {
      fun request(spec: HttpRequestSpec): HttpResponse
  }

  interface CacheBridge {
      fun get(scope: String, key: String): String?
      fun put(scope: String, key: String, value: String)
  }

  data class SourceContext(
      val source: Map<String, Any?> = emptyMap(),
      val book: Map<String, Any?> = emptyMap(),
      val chapter: Map<String, Any?> = emptyMap(),
      val variables: MutableMap<String, String> = linkedMapOf(),
      val baseUrl: String? = null,
      val cacheScope: String = "default"
  )
  ```

- [ ] **Step 4: 运行原生语义测试**

  Run: `cd runtime/legado-kotlin && ./gradlew test --tests '*NativeRuleSemanticsTest'`

  Expected: PASS for CSS/JSONPath/组合符/索引/文本结果类型；不支持的 Android 专属调用必须返回明确异常而不是空结果。

- [ ] **Step 5: 提交**

  ```bash
  git add runtime/legado-kotlin
  git commit -m "feat: vendor legado analyzer semantics behind headless ports"
  ```

### Task 3: 实现 Kotlin stdio JSON-RPC runtime

**Files:**
- Create: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/protocol/RuntimeProtocol.kt`
- Create: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/protocol/RuntimeError.kt`
- Create: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/protocol/RuntimeServer.kt`
- Modify: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/Main.kt`
- Create: `runtime/legado-kotlin/src/test/kotlin/io/legado/headless/RuntimeProtocolTest.kt`
- Create: `runtime/legado-kotlin/src/test/kotlin/io/legado/headless/RuntimeServerTest.kt`

- [ ] **Step 1: 写协议失败测试**

  ```kotlin
  @Test fun ping_returns_protocol_and_engine_revision() {
      val response = RuntimeServer().dispatchLine("{\"id\":\"1\",\"op\":\"ping\",\"protocol_version\":1}")
      assertTrue(response.success)
      assertEquals("1", response.id)
      assertEquals(1, response.protocolVersion)
      assertEquals("legado-kotlin", response.trace.engine)
  }

  @Test fun malformed_json_has_stable_error_code() {
      val response = RuntimeServer().dispatchLine("not-json")
      assertFalse(response.success)
      assertEquals("MALFORMED_REQUEST", response.error.code)
  }
  ```

- [ ] **Step 2: 运行测试确认失败**

  Run: `cd runtime/legado-kotlin && ./gradlew test --tests '*Runtime*Test'`

  Expected: FAIL because protocol models and dispatcher do not exist.

- [ ] **Step 3: 实现协议和操作分发**

  `RuntimeRequest` 至少包含 `id`、`protocol_version`、`op`、`stage`、`rule`、`content`、`content_type`、`base_url`、`redirect_url`、`context` 和 `options`；`RuntimeResponse` 必须返回 `id`、`success`、`value`、`value_type`、`trace` 和可选 `error`。

  第一批操作固定为：

  - `ping`
  - `capabilities`
  - `extract_string`
  - `extract_list`
  - `extract_elements`
  - `resolve_url`

  stdout 只输出一行 JSON，任何异常转换成稳定错误码；`options.timeout_ms` 和响应字节限制由 server 强制执行。

- [ ] **Step 4: 运行 Kotlin 协议测试**

  Run: `cd runtime/legado-kotlin && ./gradlew test --tests '*Runtime*Test'`

  Expected: PASS；另外执行 `printf '%s\n' '{"id":"1","op":"ping","protocol_version":1}' | ./gradlew run --quiet`，输出一行 `success=true` 的 JSON。

- [ ] **Step 5: 提交**

  ```bash
  git add runtime/legado-kotlin
  git commit -m "feat: add legado runtime stdio protocol"
  ```

### Task 4: 实现 Python native client 和统一 Facade

**Files:**
- Create: `backend/app/infrastructure/legado/engine/native_models.py`
- Create: `backend/app/infrastructure/legado/engine/native_runtime_client.py`
- Create: `backend/app/infrastructure/legado/engine/runtime_facade.py`
- Modify: `backend/app/infrastructure/legado/engine/__init__.py`
- Create: `backend/tests/test_native_runtime_client.py`
- Create: `backend/tests/test_runtime_facade.py`

- [ ] **Step 1: 写进程和回退失败测试**

  在测试文件顶部提供一个只处理 `ping` 的可执行 fake runtime，并让 `FakeFallback` 记录调用次数：

  ```python
  @pytest.fixture
  def fake_runtime_binary(tmp_path):
      script = tmp_path / "fake_runtime.py"
      script.write_text(
          "import json, sys\n"
          "for line in sys.stdin:\n"
          "    req = json.loads(line)\n"
          "    print(json.dumps({'id': req['id'], 'success': True, 'value': [], 'trace': {'engine': 'fake'} }), flush=True)\n",
          encoding="utf-8",
      )
      script.chmod(0o755)
      return [sys.executable, str(script)]

  class FakeFallback:
      def __init__(self):
          self.call_count = 0
      def extract(self, *args, **kwargs):
          self.call_count += 1
          return RuntimeResult(success=True, value=["fallback"])

  class FakeClient:
      def __init__(self):
          self.call_count = 0
          self.fallback = FakeFallback()
      def call(self, *args, **kwargs):
          self.call_count += 1
          return RuntimeResult(success=True, value=[])

  @pytest.fixture
  def fake_client():
      return FakeClient()

  def test_client_restarts_after_eof(fake_runtime_binary):
      client = NativeRuntimeClient(command=fake_runtime_binary)
      assert client.ping().success
      client._process.kill()
      assert client.ping().success
      assert client.restart_count == 1

  def test_facade_does_not_fallback_on_semantic_empty_result(fake_client):
      facade = LegadoRuntimeFacade(native_client=fake_client, fallback=FakeFallback())
      result = facade.extract("<div></div>", "#missing@text", stage="content")
      assert result.success
      assert result.value == []
      assert fake_client.call_count == 1
      assert fake_client.fallback.call_count == 0
  ```

- [ ] **Step 2: 运行测试确认失败**

  Run: `cd backend && pytest tests/test_native_runtime_client.py tests/test_runtime_facade.py -q`

  Expected: FAIL because the models, client and Facade are absent.

- [ ] **Step 3: 实现协议模型和 client**

  `NativeRuntimeClient` 使用 `subprocess.Popen` 启动 `java -jar`，stdin/stdout 使用 UTF-8 行协议；每个请求生成唯一 ID，读取时使用 deadline；遇到 `EOF`、`BrokenPipeError`、非法 JSON、超时或响应过大时关闭并重启子进程，返回 `RUNTIME_UNAVAILABLE`、`WORKER_EOF`、`MALFORMED_RESPONSE`、`EXECUTION_TIMEOUT` 或 `RESPONSE_TOO_LARGE`。

  最小接口固定为：

  ```python
  class NativeRuntimeClient:
      def ping(self) -> RuntimeResult: ...
      def capabilities(self) -> RuntimeResult: ...
      def call(self, operation: str, payload: dict, timeout: float) -> RuntimeResult: ...
      def close(self) -> None: ...
  ```

  `LegadoRuntimeFacade` 提供 `extract_string`、`extract_list`、`extract_elements` 和 `resolve_url`，并通过 `RuntimeMode` 支持 `native_kotlin`、`python_shadow`、`python_primary`。默认仍设为 `python_primary`，直到 Task 7 的影子测试达到切换门槛。

  `native_models.py` 先固定结果模型，避免 client、Facade 和测试各自定义字段：

  ```python
  from dataclasses import dataclass, field
  from typing import Any

  @dataclass
  class RuntimeResult:
      success: bool
      value: Any = None
      value_type: str | None = None
      trace: dict[str, Any] = field(default_factory=dict)
      error_code: str | None = None
      error: str | None = None
  ```

- [ ] **Step 4: 运行 Python 契约测试**

  Run: `cd backend && pytest tests/test_native_runtime_client.py tests/test_runtime_facade.py -q`

  Expected: PASS；同时确认 `python -c 'from app.infrastructure.legado.engine import LegadoRuntimeFacade'` 成功。

- [ ] **Step 5: 提交**

  ```bash
  git add backend/app/infrastructure/legado/engine backend/tests/test_native_runtime_client.py backend/tests/test_runtime_facade.py
  git commit -m "feat: add native runtime client and facade"
  ```

### Task 5: 接入 HTTP、Cookie、缓存和 JS bridge

**Files:**
- Create: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/protocol/BridgeMessage.kt`
- Modify: `runtime/legado-kotlin/src/main/kotlin/io/legado/headless/protocol/RuntimeServer.kt`
- Create: `backend/app/infrastructure/legado/engine/runtime_bridge.py`
- Modify: `backend/app/infrastructure/legado/engine/native_runtime_client.py`
- Modify: `backend/app/infrastructure/legado/engine/js_runtime.py`
- Create: `backend/tests/test_runtime_bridge.py`
- Modify: `backend/tests/test_js_http_bridge.py`

- [ ] **Step 1: 写 bridge 失败测试**

  测试文件中的 fake client 必须固定请求记录并提供一个可控延迟：

  ```python
  import time
  from app.infrastructure.legado.engine.http_client import HttpResponse

  class FakeHttp:
      def __init__(self, delay=0):
          self.delay = delay
          self.calls = []
      def request_sync(self, method, url, **kwargs):
          self.calls.append((method, url))
          if self.delay:
              time.sleep(self.delay)
          return HttpResponse(url=url, status=200, text="ok", headers={}, is_html=False)

  def test_bridge_request_uses_existing_http_client(fake_http):
      bridge = RuntimeBridge(http_client=fake_http, cache={})
      response = bridge.handle({"method": "GET", "url": "https://example.test"})
      assert response["status"] == 200
      assert fake_http.calls == [("GET", "https://example.test")]

  def test_bridge_timeout_returns_stable_error(fake_slow_http):
      bridge = RuntimeBridge(http_client=fake_slow_http, timeout=0.01)
      response = bridge.handle({"method": "GET", "url": "https://example.test"})
      assert response["error_code"] == "BRIDGE_TIMEOUT"
  ```

- [ ] **Step 2: 运行测试确认失败**

  Run: `cd backend && pytest tests/test_runtime_bridge.py -q`

  Expected: FAIL because `RuntimeBridge` does not exist.

- [ ] **Step 3: 实现双向 bridge**

  Kotlin 在执行 JS `java.get/post/ajax` 时输出 `bridge_http` 消息并暂停当前请求；Python 处理请求后发送 `bridge_http_result`，继续读取同一请求的最终响应。bridge payload 必须包含 method、url、headers、body、timeout_ms、cookie_scope；响应包含 status、headers、body、final_url、charset、timing 和 error_code。

  `RuntimeBridge` 必须复用 `LegadoHttpClient`，不能直接新增第二套 HTTP 实现。缓存读写通过 `CacheBridge` 映射到 `JsRuntime` 当前 source scope，禁止跨 source 泄漏。

- [ ] **Step 4: 运行 JS/bridge 回归**

  Run: `cd backend && pytest tests/test_runtime_bridge.py tests/test_js_http_bridge.py tests/test_js_runtime_worker.py -q`

  Expected: PASS；现有 Node worker 测试不得回退。

- [ ] **Step 5: 提交**

  ```bash
  git add runtime/legado-kotlin backend/app/infrastructure/legado/engine backend/tests
  git commit -m "feat: bridge legado native runtime to platform http and cache"
  ```

### Task 6: 将现有 RuleSelector 和 Fetcher 接到 Facade

**Files:**
- Modify: `backend/app/infrastructure/legado/engine/rule_selector.py`
- Modify: `backend/app/infrastructure/legado/legado_fetcher.py`
- Modify: `backend/app/infrastructure/legado/engine/executor.py`
- Modify: `backend/app/infrastructure/legado/engine/validator.py`
- Create: `backend/tests/test_runtime_facade_integration.py`
- Modify: `backend/tests/test_legado_engine_compatibility.py`
- Modify: `backend/tests/test_search_url_js_execution.py`

- [ ] **Step 1: 写 integration 失败测试**

  测试文件先定义最小书源和记录 stage 的 fake Facade：

  ```python
  import pytest
  from app.infrastructure.legado.engine.native_models import RuntimeResult

  SOURCE = {
      "bookSourceName": "example",
      "bookSourceUrl": "https://example.test/",
      "searchUrl": "/search?q={{key}}",
      "ruleSearch": {"bookList": ".book", "name": "a@text", "bookUrl": "a@href"},
  }

  class RecordingFacade:
      def __init__(self):
          self.stages = []
      def begin_session(self, **context):
          self.stages.append(context["stage"])
      def extract_list(self, *args, **kwargs):
          return RuntimeResult(success=True, value=[{"name": "剑来", "bookUrl": "/book/1"}])

  class FakeHttp:
      def __init__(self, responses):
          self.responses = responses
      async def get(self, url, **kwargs):
          return HttpResponse(url=url, status=200, text=self.responses.get(url, ""), headers={}, is_html=True)

  @pytest.fixture
  def fake_facade():
      return RecordingFacade()

  @pytest.fixture
  def fake_http():
      return FakeHttp({"/search?q=%E5%89%91%E6%9D%A5": "<a class='book' href='/book/1'>剑来</a>"})

  @pytest.mark.asyncio
  async def test_fetcher_uses_facade_for_search_toc_content(fake_facade, fake_http):
      fetcher = LegadoBookSourceFetcher(http_client=fake_http, runtime_facade=fake_facade)
      result = await fetcher.search(SOURCE, "剑来")
      assert result[0]["name"] == "剑来"
      assert fake_facade.stages == ["search"]
  ```

- [ ] **Step 2: 运行现有引擎测试确认接口尚未接通**

  Run: `cd backend && pytest tests/test_legado_engine_compatibility.py tests/test_search_url_js_execution.py -q`

  Expected: 新 integration 测试 FAIL；现有测试保持原有基线结果。

- [ ] **Step 3: 接入 Facade 且保持外部返回结构**

  `RuleSelector.extract` 和 `extract_list` 接受可选 `runtime_facade`；没有传入时通过依赖注入获取单例。Fetcher 的 `search`、`get_book_info`、`get_toc`、`get_content` 在每个 stage 建立 session，把 source/book/chapter/base URL/redirect URL 传给 Facade。纯 Python 路径只作为 Facade 的 fallback，不在业务层写 `if kotlin` 分支。

  `searchUrl` 的纯 `@js:`、目录 `tocUrl`、正文 `nextContentUrl` 均走同一上下文协议；空结果不触发无条件回退。

- [ ] **Step 4: 运行回归测试**

  Run: `cd backend && pytest tests/test_runtime_facade_integration.py tests/test_legado_engine_compatibility.py tests/test_search_url_js_execution.py tests/test_legado_request_config.py -q`

  Expected: PASS；search/toc/content 的返回 JSON 与旧 API 保持兼容。

- [ ] **Step 5: 提交**

  ```bash
  git add backend/app/infrastructure/legado backend/tests
  git commit -m "refactor: route source parsing through runtime facade"
  ```

### Task 7: 建立 Kotlin/Python 黄金语料和影子差异门槛

**Files:**
- Create: `backend/tests/fixtures/legado_runtime/html_rules.json`
- Create: `backend/tests/fixtures/legado_runtime/json_rules.json`
- Create: `backend/tests/fixtures/legado_runtime/js_rules.json`
- Create: `backend/tests/fixtures/legado_runtime/url_rules.json`
- Create: `backend/tests/test_legado_native_runtime_diff.py`
- Create: `backend/scripts/run_legado_diff.py`
- Modify: `backend/app/infrastructure/legado/engine/runtime_facade.py`

- [ ] **Step 1: 写差异测试和失败样本**

  每个 fixture 使用 `{content, rule, mode, base_url, expected_value, expected_type}`；至少包含 CSS 负索引、`@CSS:`、XPath、JSONPath 内嵌、Regex 替换、`@put`、JS `return result`、相对 URL 和分页选项。

  测试必须比较 `value`、`value_type`、`url`、`variables` 和 `error.code`，而不是只比较是否非空。

- [ ] **Step 2: 运行差异测试确认存在记录**

  Run: `cd backend && python scripts/run_legado_diff.py --fixtures tests/fixtures/legado_runtime --format json`

  Expected: 输出每条规则的 engine、success、diff 字段；当前尚未完全切换时允许记录差异，但命令必须以非零退出码标示未解释差异。

- [ ] **Step 3: 实现 shadow 模式**

  当 `runtime_mode=python_shadow` 时，Facade 先以 Kotlin 结果作为主结果，再异步/受限地执行 Python 对照；差异写入结构化日志和 `RuntimeDiff`，不改变主结果。差异记录包括 source_id、stage、rule hash、输入摘要、两侧值摘要、error code 和 engine revisions，禁止记录完整敏感 Cookie/API key。

- [ ] **Step 4: 运行黄金语料**

  Run: `cd backend && pytest tests/test_legado_native_runtime_diff.py -q`

  Expected: 所有已声明等价的 fixture PASS；未等价样本必须显示具体字段和归因，不得被 `xfail` 或忽略列表隐藏。

- [ ] **Step 5: 提交**

  ```bash
  git add backend/tests/fixtures/legado_runtime backend/tests/test_legado_native_runtime_diff.py backend/scripts/run_legado_diff.py backend/app/infrastructure/legado/engine/runtime_facade.py
  git commit -m "test: add legado native golden corpus and shadow diffs"
  ```

### Task 8: 单容器构建、启动和健康治理

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `docker-compose.yml`
- Create: `backend/app/infrastructure/legado/engine/runtime_process.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/interfaces/api/v0/status.py`
- Create: `backend/tests/test_runtime_process.py`
- Modify: `backend/tests/test_legado_fetcher_close.py`

- [ ] **Step 1: 写生命周期失败测试**

  ```python
  @pytest.mark.asyncio
  async def test_lifespan_closes_native_runtime_and_node_worker(fake_app):
      async with lifespan(fake_app):
          assert fake_app.state.runtime.started
      assert fake_app.state.runtime.closed
      assert fake_app.state.js_worker.closed
  ```

- [ ] **Step 2: 运行测试确认生命周期未接入**

  Run: `cd backend && pytest tests/test_runtime_process.py tests/test_legado_fetcher_close.py -q`

  Expected: 新测试 FAIL；现有 close 测试记录当前基线。

- [ ] **Step 3: 修改 Docker multi-stage 构建**

  构建阶段使用 JDK 17 和 Gradle wrapper 编译 `runtime/legado-kotlin` fat JAR；运行阶段在 `python:3.11-slim-bookworm` 安装 `openjdk-17-jre-headless` 和 `tini`，复制 JAR 到 `/app/runtime/legado-runtime.jar`。最终 CMD 使用：

  ```dockerfile
  ENTRYPOINT ["/usr/bin/tini", "--"]
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

  Compose 保持一个 `legado-hub` 应用容器，不新增 runtime service；健康检查调用 `/api/status` 并验证 `runtime_state`。

- [ ] **Step 4: 实现进程管理和状态接口**

  `RuntimeProcessManager` 负责懒启动、ping、超时终止、重启计数、stderr 采集和优雅关闭。`/api/status` 增加 `runtime.engine`、`runtime.protocol_version`、`runtime.state`、`runtime.restart_count` 和最近错误 code，但不暴露命令行或密钥。

- [ ] **Step 5: 运行容器验证**

  Run: `docker build -f backend/Dockerfile -t legado-hub-native-runtime .`

  Run: `docker run --rm legado-hub-native-runtime python -c 'import urllib.request; print("image-ok")'`

  Run: `docker compose config`

  Expected: image build succeeds；镜像内存在 `java -version`、`node --version` 和 `/app/runtime/legado-runtime.jar`；Compose 不出现第二个 runtime 服务。

- [ ] **Step 6: 提交**

  ```bash
  git add backend/Dockerfile docker-compose.yml backend/app/main.py backend/app/infrastructure/legado/engine backend/tests
  git commit -m "build: run native legado runtime in one container"
  ```

### Task 9: 迁移业务流程并接入 Agent、写源和探针

**Files:**
- Modify: `backend/app/infrastructure/legado/legado_fetcher.py`
- Modify: `backend/app/application/services/source_probe_service.py`
- Modify: `backend/app/application/services/interactive_browser_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/interfaces/api/v0/engine.py`
- Modify: `backend/app/interfaces/api/v0/test.py`
- Create: `backend/tests/test_native_runtime_source_flow.py`
- Modify: `backend/tests/test_source_probe_service.py`
- Modify: `backend/tests/test_api_engine_runtime.py`

- [ ] **Step 1: 写 search→toc→content 端到端失败测试**

  在测试文件中用 `FakeHttpTransport` 返回固定 search/detail/toc/content 页面，用 `RecordingFacade` 收集 stage；断言四个 stage 均有 runtime trace，内容失败时返回 `CONTENT_PARSE_ERROR` 或明确 HTTP 错误，而不是 `unknown`：

  ```python
  @pytest.mark.asyncio
  async def test_native_source_flow_records_each_stage(fake_transport, native_runtime):
      fetcher = LegadoBookSourceFetcher(http_client=fake_transport, runtime_facade=native_runtime)
      books = await fetcher.search(SOURCE, "剑来")
      toc = await fetcher.get_toc(SOURCE, books[0]["bookUrl"])
      content = await fetcher.get_content(SOURCE, toc[0]["url"])
      assert content["content"]
      assert [item.stage for item in native_runtime.traces] == ["search", "toc", "content"]
  ```

- [ ] **Step 2: 运行端到端测试确认尚未切换**

  Run: `cd backend && pytest tests/test_native_runtime_source_flow.py -q`

  Expected: FAIL until Facade、runtime process 和 fetcher wiring 完成。

- [ ] **Step 3: 切换依赖注入和 stage context**

  工厂只创建一个 `LegadoRuntimeFacade` 实例并注入 fetcher、engine service、source probe 和 Agent tool adapter。每个 stage 传递 source、book、chapter、base URL、redirect URL、variables 和 cache scope；健康探针复用相同 Facade，不另起解析器。

  写源引擎在验证候选源时必须保存 runtime trace 和 error code；Agent 工具返回结构化检索证据，禁止在 runtime 失败时用模型常识填充书籍内容。

- [ ] **Step 4: 运行业务回归和真实源 smoke**

  Run: `cd backend && pytest tests/test_native_runtime_source_flow.py tests/test_source_probe_service.py tests/test_api_engine_runtime.py tests/test_search_douluo.py -q`

  Run: `cd backend && python scripts/run_legado_diff.py --real-source-suite --max-sources 5`

  Expected: 现有 API、探针和真实源测试通过；每次失败都带 stage、runtime/error code、请求证据和最终 URL。

- [ ] **Step 5: 提交**

  ```bash
  git add backend/app backend/tests
  git commit -m "feat: migrate source agent and health flows to native legado runtime"
  ```

### Task 10: 稳定运行后逐模块迁移 Python

**Files:**
- Modify: `backend/app/infrastructure/legado/engine/parser.py`
- Modify: `backend/app/infrastructure/legado/engine/text_pipeline.py`
- Modify: `backend/app/infrastructure/legado/engine/url_utils.py`
- Modify: `backend/app/infrastructure/legado/engine/runtime_facade.py`
- Create: `backend/tests/test_python_module_parity.py`
- Modify: `backend/tests/test_legado_native_runtime_diff.py`

- [ ] **Step 1: 固定迁移门槛**

  在 `runtime_facade.py` 中只允许下列条件同时满足时把模块设为 `python_primary`：

  ```python
  MIGRATION_GATE = {
      "max_unexplained_diffs": 0,
      "golden_cases": 100,
      "real_source_runs": 20,
      "fallback_rate": 0.0,
  }
  ```

  该门槛只针对纯模块；JS、Jsoup、XPath 和复杂 `AnalyzeUrl` 保持 Kotlin 主路径。

- [ ] **Step 2: 先迁移规则切分和文本纯函数**

  为 `parser.py`、`text_pipeline.py` 增加与 Kotlin fixture 一一对应的测试；每个函数执行 Kotlin shadow 并比较 AST、列表顺序、替换结果和错误 code。任何差异都保留 Kotlin 结果并记录 `python_shadow_diff`。

- [ ] **Step 3: 运行迁移测试**

  Run: `cd backend && pytest tests/test_python_module_parity.py tests/test_legado_native_runtime_diff.py -q`

  Expected: 只有满足 `MIGRATION_GATE` 的模块允许切换；其他模块仍显示 `native_kotlin`。

- [ ] **Step 4: 提交每个通过门槛的模块**

  ```bash
  git add backend/app/infrastructure/legado/engine backend/tests
  git commit -m "refactor: migrate verified legado pure module to python"
  ```

### Task 11: 全量验证、发布和回滚演练

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CODE_GUIDE.md`
- Create: `docs/superpowers/reports/2026-07-18-legado-native-runtime-acceptance.md`
- Create: `backend/tests/test_runtime_failure_recovery.py`

- [ ] **Step 1: 写故障恢复测试**

  覆盖 JVM EOF、协议损坏、JS timeout、HTTP bridge timeout、响应过大和 Docker SIGTERM；断言服务仍可用、重启计数递增、回退原因可见、没有僵尸子进程。

- [ ] **Step 2: 运行分层测试**

  ```bash
  cd backend
  pytest tests/test_native_runtime_client.py tests/test_runtime_facade.py tests/test_runtime_bridge.py -q
  pytest tests/test_legado_native_runtime_diff.py tests/test_native_runtime_source_flow.py -q
  pytest -q
  ```

  Expected: 新增测试全部通过；全量测试若有既有失败，必须记录原始失败和是否与本次改动相关，不得删除或屏蔽测试。

- [ ] **Step 3: 构建并执行单容器 smoke**

  ```bash
  docker build -f backend/Dockerfile -t legado-hub:native-runtime .
  docker compose up -d legado-hub
  curl -fsS http://127.0.0.1:8000/api/status
  docker compose restart legado-hub
  curl -fsS http://127.0.0.1:8000/api/status
  ```

  Expected: 重启前后 runtime 能力、健康状态和 API 响应正常。

- [ ] **Step 4: 运行真实源验收并写报告**

  对至少 5 个稳定来源执行 search/toc/content，对含 JS、JSON、XPath、分页和相对 URL 的来源分别记录结果、耗时、trace、错误码和 fallback 率；Cloudflare/网络失败必须与解析失败分开。

- [ ] **Step 5: 更新文档并提交**

  在 `docs/ARCHITECTURE.md` 说明单容器内部进程、Facade、协议和回退；在报告中记录 commit、镜像 digest、测试命令和真实源结果。

  ```bash
  git add docs backend/tests/test_runtime_failure_recovery.py
  git commit -m "test: verify native legado runtime recovery and acceptance"
  ```

## 执行顺序和检查点

按 Task 1→11 顺序执行。每个 Task 必须先写失败测试，再实现最小代码，再运行指定测试并提交。Task 4 完成后可以在不改变业务默认行为的情况下合并；Task 8 完成后才允许在本地 Docker 启动 Kotlin runtime；Task 9 的真实源验收通过后才允许将 `native_kotlin` 设为默认；Task 10 永远是可选的渐进优化，不能阻塞 Kotlin 原生内核发布。

## 计划自检

- 许可证、上游 commit、headless 边界和 GPL-3.0 说明覆盖设计文档第 2 节。
- 单容器、tini、JVM 进程、Node worker、stdio 协议和资源治理覆盖第 4–6 节。
- 默认 Kotlin、可观测回退、shadow diff 和逐步 Python 迁移覆盖第 7–8 节。
- HTTP/Cookie/Cache/JS bridge、安全限制和错误码覆盖第 5.1、6、9 节。
- 黄金语料、差异测试、真实源、故障恢复和发布回滚覆盖第 10–11 节。
- 已扫描计划中的 `TODO`、`TBD` 和未定义函数名；每个代码步骤均给出文件、接口、命令或预期结果。
