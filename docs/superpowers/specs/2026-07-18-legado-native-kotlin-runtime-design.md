# Legado 原生 Kotlin 解析内核与单容器平台化设计

> 日期：2026-07-18  
> 项目：LegadoHub Pro
> 目标：以官方“阅读”稳定版的可观察行为为兼容标准，复用 `HapeLee/legado-with-MD3` 的 GPL-3.0 实现，并在单 Docker 容器内为平台提供模块化运行时。

## 1. 背景与目标

当前后端已经具备 Python 规则选择器、JSONPath 扩展、文本处理、URL 工具、Node JS worker 和书源抓取流程，但这些组件是逐步补齐的兼容实现。官方 Legado 的规则语义包含大量容易被忽略的细节，例如嵌套规则切分、CSS 索引、规则组合符、`@put`/`@get`/`{{ }}`、相对 URL、重定向、JS 共享作用域和缓存生命周期。

本设计的目标是：

1. 直接复用参考仓库中已经验证过的解析语义，避免重新翻译整套内核。
2. 以单个 Docker 容器交付，不增加独立 runtime 容器或内部网络服务。
3. 通过 Python Facade 将 Kotlin 内核、HTTP/缓存桥接、旧引擎回退和业务流程解耦。
4. 在稳定运行后，以差异测试为依据，逐步把适合的纯模块迁移为 Python；JS、Jsoup、XPath 等高风险语义在没有证据前继续使用 Kotlin。
5. 让每次回退、差异、超时和不支持能力都可观测、可追踪、可回滚。

本设计不承诺一次性复制整个 Android 应用，也不把 UI、数据库、阅读界面或与平台无关的功能带入后端。

## 2. 许可证与上游边界

参考仓库：`https://github.com/HapeLee/legado-with-MD3`  
锁定的调研基线 commit：`2c340d48bb1b9537690ec31eb9c23a57307f30a3`  
许可证：GPL-3.0。

项目将补充 GPL-3.0 LICENSE，并在 `THIRD_PARTY_NOTICES.md` 中记录：

- 上游仓库、commit、版权和许可证；
- 直接复用的文件或目录；
- 平台适配补丁和修改日期；
- 未复用、由平台独立实现的代码范围。

上游代码以受控 vendor 子树或明确的上游快照方式维护。修改版必须保留原有版权与许可证声明，并在发布镜像时提供对应源代码。

## 3. 方案比较与结论

### 方案 A：直接使用 Kotlin 原生内核（采用）

将参考仓库的解析相关代码抽成 headless Kotlin/JVM 模块，通过本地 stdio JSON-RPC 与 Python 通信。该方案最接近官方行为，能够复用规则解析、JSoup、XPath、JSONPath、Regex、Rhino 和 URL 语义。

代价是镜像增加 JRE、需要 Android 依赖替换和子进程治理，但这些成本是确定的、可测试的。

### 方案 B：全部翻译为 Python（不作为第一阶段）

部署简单、与现有后端融合自然，但实际等同于重写解析内核。规则平衡切分、选择器索引、Rhino 类型转换和共享 JS scope 等差异很难通过常规单元测试完全发现，不能满足当前“官方语义优先”的要求。

### 方案 C：Kotlin 基线 + Python 渐进迁移（长期路线）

先让 Kotlin 成为默认参考实现，同时保留旧 Python/Node 引擎作为受控回退和影子对照。只有当某个纯模块通过黄金样本、真实书源和差异回归后，才允许迁移为 Python。该方案在稳定性和未来简化部署之间取得平衡。

## 4. 单容器总体架构

```text
┌──────────────────────────── legado-hub 容器 ────────────────────────────┐
│                                                                         │
│  tini (PID 1)                                                           │
│      └── uvicorn / FastAPI                                               │
│            ├── LegadoRuntimeFacade                                      │
│            │      ├── legado-runtime.jar (stdio JSON-RPC, 常驻)         │
│            │      └── Python/Node fallback (受控、可观测)               │
│            ├── LegadoHttpClient / Cookie / Cache / Proxy                 │
│            └── 现有 Agent、探针、书源 API                                │
│                                                                         │
│  node legado_js_worker.js（按需常驻）                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

Kotlin runtime 不监听端口，不加入 Docker Compose 服务列表，也不承担外部 HTTP 入口。Python 通过本地管道发送请求，避免容器间网络、服务发现和版本错配。

### 4.1 Python 业务边界

新增唯一入口 `LegadoRuntimeFacade`，业务层只依赖该接口：

- `parse_rule(rule, mode, options)`：解析并缓存规则 AST/执行计划；
- `extract(content, rule, context)`：执行字符串、列表或元素提取；
- `resolve_url(rule_url, base_url, redirect_url, options)`：解析 URL 规则；
- `execute_js(code, context)`：执行原生 JS 规则；
- `begin_session(source, book, chapter, stage)` / `end_session()`：控制上下文和缓存生命周期；
- `health()` / `capabilities()`：报告 runtime 可用性和能力版本。

`LegadoBookSourceFetcher`、Agent 工具、健康探针、写源引擎和 API 路由均通过 Facade 使用内核，不直接 import Kotlin client、旧 `RuleSelector` 或 Node worker。

### 4.2 Kotlin headless 模块

在 `runtime/legado-kotlin/` 中维护以下模块边界：

- `analyzeRule`：`AnalyzeRule`、`RuleAnalyzer`、`RuleData`、规则模式识别和规则链编排；
- `selectors`：JSoup、XPath、JSONPath、Regex 适配；
- `url`：`AnalyzeUrl`、分页参数、请求选项、相对地址和重定向；
- `js`：Rhino 执行、脚本缓存、共享 scope 和原生变量注入；
- `headless`：平台端口实现、JSON-RPC 入口、资源限制和错误归一化。

Android UI、Room、Activity、WebView 界面和阅读业务不进入 headless 模块。需要平台行为的组件改为端口接口：`HttpBridge`、`CookieBridge`、`CacheBridge`、`LogBridge`、`CancellationBridge` 和 `ScopeBridge`。

## 5. 本地 JSON-RPC 协议

协议采用一行一个 JSON 消息，所有请求和响应带 `id`。stdout 只输出协议消息，诊断日志输出 stderr，由 Python 统一收集。

请求示例：

```json
{
  "id": "req-123",
  "protocol_version": 1,
  "op": "extract",
  "stage": "content",
  "source_id": "source.example",
  "rule": "id.content@textNodes",
  "content": "<div id=\"content\">...</div>",
  "content_type": "html",
  "base_url": "https://example.com/book/1/",
  "redirect_url": "https://example.com/book/1/",
  "context": {
    "source": {},
    "book": {},
    "chapter": {},
    "variables": {},
    "cache_scope": "source:source.example"
  },
  "options": {
    "trace": true,
    "timeout_ms": 10000
  }
}
```

响应至少包含：

```json
{
  "id": "req-123",
  "success": true,
  "value": ["正文"],
  "value_type": "list",
  "trace": {
    "engine": "legado-kotlin",
    "engine_commit": "2c340d48...",
    "steps": [],
    "elapsed_ms": 8,
    "cache_reads": [],
    "cache_writes": []
  },
  "error": null
}
```

错误统一为稳定 code，例如 `RULE_SYNTAX_ERROR`、`SELECTOR_UNSUPPORTED`、`JS_TIMEOUT`、`BRIDGE_TIMEOUT`、`RUNTIME_UNAVAILABLE`、`PAYLOAD_TOO_LARGE`。不允许只返回空字符串而丢失原因。

### 5.1 HTTP/缓存桥接

Kotlin JS 中的 `java.get/post/ajax` 不直接拥有平台网络权限，而是发送桥接消息给 Python。Python 使用既有 `LegadoHttpClient` 执行请求，返回状态码、headers、正文、最终 URL、charset、cookie 变更和 timing。这样可以保持代理、Cookie、重试、限流和审计的一致性。

缓存分为：

- source session cache：对应官方 source 共享作用域；
- book/chapter variables：对应 `RuleDataInterface`；
- platform response cache：由 Python HTTP 层管理。

## 6. 进程生命周期与资源治理

- Docker 使用 `tini` 作为 PID 1；
- FastAPI lifespan 启动时只检查 runtime，首次需要解析时再启动 JAR；
- Python 默认维护一个常驻 runtime client，并通过有界队列串行化请求以保护 JS 共享作用域；只有压测证明需要并发时，才在同一容器内启动多个同版本 JAR 子进程组成池；
- 每次请求有 deadline，Kotlin 超时后进程被终止并重新拉起；
- JVM 通过 `-Xms32m -Xmx256m`、线程上限和响应字节上限进行约束；
- 容器停止时先停止新任务，再关闭 Node worker 和 Kotlin runtime；
- runtime stderr 按请求 ID 写入应用日志，避免子进程日志丢失；
- `/api/status` 和健康检查报告 `runtime_state`、版本、能力和最近错误。

Docker 构建采用多阶段：构建阶段使用 JDK/Gradle 编译 headless fat JAR，最终 Python 镜像只安装 JRE、Node 和运行时依赖。

## 7. 回退与迁移策略

### 7.1 默认路径

稳定后默认顺序为：

1. Kotlin 原生 runtime；
2. 仅当 runtime 不可用、桥接失败或能力明确不支持时，进入 Python/Node fallback；
3. fallback 必须在 trace 中标记 `fallback_reason`，不能把语义错误伪装成成功。

解析结果为空不自动回退，因为“空结果”可能是规则本身正确返回空，或是规则语义错误；需要依靠错误 code、能力声明和差异测试判断。

### 7.2 逐步迁移纯模块

稳定运行后，按以下顺序评估 Python 迁移：

1. 规则切分和规则 AST（纯字符串逻辑）；
2. 文本替换、正则和列表组合；
3. 不涉及 JS 的 URL 规范化；
4. 其他通过差异测试证明等价的纯函数。

以下模块默认继续使用 Kotlin，除非达到零未解释差异：JS/Rhino、JSoup 选择器、XPath、复杂 JSONPath、`AnalyzeUrl` 的脚本和请求选项语义。

每个迁移模块使用 feature flag：`native_kotlin`、`python_shadow`、`python_primary`。旧实现只有在该模块的黄金样本和真实源回归均通过后才可成为主路径。

## 8. 业务迁移顺序

1. 接入 Facade，不改变 API 和返回结构；
2. 影子执行现有规则，记录 Kotlin/Python 差异；
3. 迁移 `search`；
4. 迁移 `book_info` 和 `toc`；
5. 迁移 `content`、下一章 URL 和分页；
6. 接入写源引擎、Agent 检索工具和健康探针；
7. 通过真实源验收后，逐步扩大 Kotlin 默认流量；
8. 最后再决定是否移除旧 Python selector，保留可回滚版本。

## 9. 安全与可靠性

- JS 执行必须有 CPU/墙钟超时、内存上限和调用深度限制；
- Kotlin runtime 使用非特权用户运行，禁止访问宿主敏感路径；
- HTTP bridge 应用现有域名、代理、请求头和并发策略；
- 单次输入、脚本、响应和 trace 均设置大小上限；
- 所有外部 URL 仍由平台请求策略校验；
- 子进程异常、协议破坏、JSON 解析失败和桥接超时都产生稳定错误码；
- 未知规则能力进入候选/诊断状态，不得自动发布为“可用”。

## 10. 测试与验收

### 10.1 单元和契约测试

- `RuleAnalyzer` 平衡组、转义、组合符和内嵌规则；
- CSS/JSoup 索引、负索引、排除和属性提取；
- XPath、JSONPath、Regex 与结果类型；
- `@put`、`@get`、`{{ }}`、`$n` 和替换规则；
- URL 相对地址、重定向、分页和请求选项；
- JSON-RPC 协议、超时、重启、响应过大和桥接错误；
- cache/session/source/book/chapter 生命周期。

### 10.2 差异测试

建立固定黄金语料，至少覆盖：

- 官方规则示例；
- 当前项目已有测试样本；
- 含 JS 的真实书源；
- 搜索、详情、目录、正文和多页正文。

同一输入分别通过 Kotlin 内核和旧 Python 引擎，比较值、类型、URL、变量和错误码。所有差异必须有归因；不能用“忽略差异”掩盖问题。

### 10.3 真实验收

对候选书源执行真实 `search -> toc -> content`，记录请求证据、规则 trace、耗时和最终内容。Cloudflare、站点失效和网络错误与解析错误分开归类。

验收通过条件：

- 现有回归测试不回退；
- 核心官方语义样本无未解释差异；
- 真实源核心流程达到质量门槛；
- runtime 重启、超时和回退路径有自动化测试；
- 旧接口和前端不需要感知内核实现变化。

## 11. 交付和回滚

每个镜像记录：后端 commit、Kotlin runtime commit、协议版本和依赖锁文件。发布前先影子运行，随后按源分组启用。任何回归都可以通过 feature flag 将主路径切回旧 Python 引擎，并保留 Kotlin trace 供修复。

本设计完成后，下一步使用实现计划拆解为：headless Kotlin 模块、JSON-RPC client、Docker 单容器构建、Facade 适配、差异测试、业务迁移和真实验收六个阶段。
