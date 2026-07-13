# 2026-07-09 JS engine enhancement design

## 背景

当前 `backend` 已经打通一部分真实书源链路，但 JS 兼容仍是核心瓶颈：

- `JsRuntime` 目前主要是少量 builtin pattern + `node -e` 一次性执行
- `LegadoBookSourceFetcher.search()` 遇到纯 `@js:` `searchUrl` 仍会直接跳过
- 复杂书源常见依赖：
  - `java.get/post/ajax`
  - `org.jsoup.Jsoup.parse`
  - `cache.putMemory/getFromMemory`
  - token/sign/crypto
  - 二次请求与多步上下文编排

本地真实数据统计显示：

- 总书源：2385
- 含任意 JS 的书源：1432
- 高频字段：
  - `ruleContent.content`: 570
  - `ruleToc.chapterUrl`: 330
  - `ruleToc.chapterList`: 315
  - `ruleSearch.coverUrl`: 283
  - `searchUrl`: 253
  - `ruleBookInfo.tocUrl`: 202

用户新增要求是：**不只是增强兼容，而是以 Legado 原生 JS 解析语义为基准，尽可能完整复刻其书源脚本行为，再做服务端平台增强。**

因此本轮目标从“保留 JS 并增强兼容”进一步提升为：

1. **行为级复刻 Legado 原生 JS 解析语义**
2. **在不破坏原生语义的前提下做服务端适配与增强**
3. **用真实书源和差异回归验证兼容度**

## 核心设计准则

### 基线定义

本设计将“完美复刻”解释为以下工程目标：

1. **语义基线**：以 `gedoor/legado` 原生书源 JS 运行语义为唯一行为基准
2. **结果优先**：默认情况下，相同书源、相同输入、相同上下文，应尽量产出与原生一致的结果
3. **增强非破坏**：服务端增强只能作为附加能力，不能静默改变默认语义
4. **差异可观测**：凡是与原生行为不一致，必须能记录、归因、回归

### 复刻范围

本轮不仅复刻 API 名称，还要复刻：

- 变量注入语义
- 执行阶段上下文
- JS 与 selector 规则串联方式
- `result/source/book/baseUrl/cache` 生命周期
- `java.*` 行为与返回值形态
- `Jsoup.parse(...).select(...)` 常见链式调用
- 书源中 `@js:` / `<js>` / inline js 的触发方式
- 失败时的默认回退和容错形态

## 目标

### 业务目标

1. 打通纯 `@js:` `searchUrl` 的真实执行链路
2. 增强 `search / toc / content / bookInfo` 中复杂 JS 规则兼容率
3. 对多步请求、缓存、上下文共享、二次解析给出统一执行通道
4. 保证已跑通的真实源不回退
5. 为“与 Legado 原生一致”建立可验证的兼容基线

### 技术目标

1. 从一次性 `node -e` 升级到长驻 Node worker
2. 由 Python 继续主控 HTTP、cookie、retry、charset、超时、并发
3. JS 侧提供更完整的 `java/cache/Jsoup/source/book/result/baseUrl` shim
4. 引入**原生语义兼容层**，明确复刻哪些原生行为
5. 为每次 JS 执行保留结构化 trace、error code、compat diff

### 非目标

1. 本阶段不追求把全部 JS 改写为纯 Python
2. 本阶段不承诺一次性对齐全部冷门 Java/Android 专属 API
3. 本阶段不以“比原生更智能”为第一目标，优先保证兼容

## 方案选型

### 方案 A：继续增强现有 one-shot Node 执行

优点：

- 改动较小
- 可以快速补少量能力

缺点：

- 每次 `node -e` 都是一次性进程
- 状态、调试、日志、崩溃恢复能力弱
- 很难稳定复刻原生上下文生命周期与多步请求语义

### 方案 B：Python 主控 + Node worker + 原生语义兼容层（推荐）

优点：

- 最适合当前真实书源兼容目标
- 能复用现有 `LegadoHttpClient`
- 便于持有会话状态、cache、trace、compat diff
- 可以把“原生行为复刻”和“服务端增强”明确分层

缺点：

- 需要新增 Python 与 Node 的协议桥接
- 需要额外建设行为对照测试与差异校验

### 方案 C：切换到嵌入式 JS 引擎

优点：

- 理论上更“内聚”

缺点：

- Windows + Python 3.13 场景下部署和兼容成本更高
- 对真实书源收益不确定
- 不利于快速接入服务端 HTTP、trace、资源隔离和进程治理

### 结论

采用 **方案 B：Python 主控 + Node worker + 原生语义兼容层**。

## 总体架构

引入统一的 **Legado Native JS Bridge**，位于 `LegadoBookSourceFetcher` 与 `JsRuntime` 之间。

### 分层

1. **Fetcher 层**
   - `LegadoBookSourceFetcher`
   - 负责 search / toc / content / bookInfo 业务流程编排

2. **Native Semantics 层**
   - `JsRuntime`
   - `JsExecutionSession`
   - `JsExecutionContext`
   - `LegadoJsCompatProfile`
   - 负责原生语义建模、上下文注入、cache 生命周期和 selector/JS 串联行为

3. **Worker Transport 层**
   - `JsWorkerClient`
   - Python 与 Node 长驻进程通过 stdin/stdout JSON 消息通信

4. **JS Shim 层**
   - Node 侧注入 `java`、`cache`、`source`、`book`、`result`、`baseUrl`
   - 提供 `org.jsoup.Jsoup.parse` 兼容接口
   - 提供与原生尽量一致的 helper/返回形态

5. **Server Enhancements 层**
   - trace
   - timeout / restart / concurrency control
   - feature flags
   - compatibility diff
   - 资源限制与隔离

### 设计原则

1. **先复刻，再增强**
2. Python 保持主控，JS 负责规则语义执行
3. 复刻层与增强层必须解耦，避免增强逻辑污染默认行为
4. 内置 builtin fast-path 只用于“已确认与原生等价”的模式
5. 与原生不一致时，优先暴露差异，而不是静默改写结果

## 组件设计

### Python 侧

#### 1. `app/infrastructure/legado/engine/js_runtime.py`

升级为门面层，职责：

- 创建和复用 worker
- 创建执行 session
- builtin fast-path 命中处理
- 派发复杂 JS 到 worker
- 接收桥接调用结果并同步 cache
- 维护 compat profile 和行为开关

建议内部抽象：

- `JsRuntime`
- `JsExecutionSession`
- `JsExecutionContext`
- `JsInvocationResult`
- `LegadoJsCompatProfile`

#### 2. `app/infrastructure/legado/engine/js_worker_bridge.py`（新增）

职责：

- 启动 Node worker
- 维护长驻进程
- 发送执行请求
- 处理返回结果、bridge call、日志、错误
- 负责超时、重启、协议校验、健康状态
- 透传 compatibility diagnostics

#### 3. `app/infrastructure/legado/engine/js_session_models.py`（新增）

建议模型：

- `JsExecutionContext`
- `JsHttpRequestSpec`
- `JsBridgeCall`
- `JsExecutionTrace`
- `JsExecutionOutput`
- `JsCompatDiff`

#### 4. `app/infrastructure/legado/engine/legado_native_semantics.py`（新增）

职责：

- 明确原生 Legado 书源脚本执行语义
- 统一变量注入规则
- 统一类型归一化、返回值封装、cache 生命周期
- 管理“默认原生模式”与“服务端增强模式”

#### 5. `app/infrastructure/legado/legado_fetcher.py`

调整为所有阶段都显式传递统一 context：

- `search()`
- `get_toc()`
- `get_content()`
- `get_book_info()`

关键变更：

- `searchUrl` 为纯 `@js:` 时不再跳过
- 允许 JS 返回：
  - 最终 URL
  - method
  - body
  - headers
  - 或已处理好的响应体
- 在每个阶段标记当前 `stage`，便于复刻原生行为与做差异记录

### Node 侧

新增：

- `backend/nodejs/legado_js_worker.js`
- `backend/nodejs/legado_shims/`

职责：

- 常驻执行
- 接收 execute 请求
- 构造与原生尽量一致的沙箱上下文
- 注入 `java/cache/source/book/result/baseUrl/org.jsoup`
- 将 `java.get/post/ajax` 转为 bridge message 请求 Python
- 用 shim 模拟原生常用行为与返回值风格

## 原生语义复刻要点

### 1. 变量与上下文

统一复刻：

- `result`
- `source`
- `book`
- `baseUrl`
- `cache`
- `key/searchKey/page` 等搜索变量
- 各阶段可见变量范围

重点不是“有没有这个变量”，而是：

- 在哪个阶段可用
- 初始值是什么
- 可变更后如何影响后续规则
- cache 跨阶段是否保留

### 2. `java.*` 行为

优先按原生行为复刻：

- `java.get`
- `java.post`
- `java.ajax`
- `java.put`
- `java.getString` / `java.get` 类缓存访问
- `java.base64Encode/Decode`
- `java.md5Encode`
- `java.randomUUID`
- 常见字符串/加密辅助函数

要求不仅 API 名称兼容，还要尽量兼容：

- 参数格式
- 返回值类型
- 对 `baseUrl/source` 的引用方式
- 常见错误场景下的表现

### 3. `org.jsoup.Jsoup.parse`

重点兼容：

- `parse(result)`
- `.select(...)`
- `.text()`
- `.html()`
- `.attr(...)`
- 常见 `Elements` / `Element` 链式访问
- 书源里常见的索引访问模式

### 4. JS 与 selector 串联

要保持与原生接近的行为：

- `@js:`
- `<js>...</js>`
- `selector + @js:` 串联
- JS 输出再交给 JSONPath/CSS/XPath
- 规则中列表 / 单值 / 文本之间的默认转换

### 5. 生命周期

统一定义：

- 单次执行 session 生命周期
- source 级 cache 生命周期
- search -> toc -> content 跨阶段共享行为
- worker 重启时哪些状态该保留，哪些必须丢弃

## 服务端增强策略

增强必须建立在“原生模式优先”的前提下。

### 增强项

1. 长驻 worker
2. 结构化 trace
3. 结构化 error code
4. compatibility diff
5. timeout / restart / health check
6. 并发隔离与资源限制
7. feature flags
8. 可回放的真实书源回归脚本

### 非破坏原则

- 默认执行结果以原生语义为准
- 增强只增加稳定性、可观测性、治理能力
- 若增强逻辑会改变结果，必须放在显式开关后

## 数据流设计

### 场景 A：`searchUrl = @js: ...`

1. `LegadoBookSourceFetcher.search()` 识别纯 JS 搜索
2. 构造 `JsExecutionContext`
3. 载入 `LegadoJsCompatProfile`
4. 调用 `JsRuntime.execute()`
5. Node worker 按原生语义执行脚本
6. 若脚本调用 `java.get/post/ajax`
   - Node 向 Python 发送 bridge call
   - Python 用 `LegadoHttpClient` 发起真实请求
   - Python 将文本/JSON/headers 等返回 Node
7. JS 返回：
   - request spec，或
   - 处理后的响应数据
8. Python 再进入现有 `ruleSearch.bookList/name/author/...` 提取链路
9. 记录 compat trace 和差异点

### 场景 B：`ruleContent.content = @js: ...`

1. Python 先请求章节页
2. 将响应内容放入 `result`
3. JS 可执行：
   - 正则提取
   - `JSON.parse`
   - `cache.putMemory`
   - `Jsoup.parse`
   - `java.post(...)` 二次请求
4. JS 返回最终正文
5. Python 再做 `replaceRule` 与文本清洗
6. 若结果与原生兼容规则存在差异，写入 diagnostics

### 场景 C：`ruleBookInfo.init` / `tocUrl`

1. Python 请求详情页
2. 将详情页数据作为 `result`
3. JS 返回：
   - 中间对象，或
   - `tocUrl` 字符串
4. Python 继续目录提取流程
5. 记录变量、cache、url 解析行为是否符合原生约定

## 兼容策略

### 保持兼容

继续兼容：

- `@js:` / inline js
- `cache.putMemory/getFromMemory`
- `result/source/book/baseUrl`
- 当前已验证与原生等价的 builtin pattern

### 优先对齐

优先补齐：

- `java.get(url)`
- `java.post(url, body)`
- `java.ajax(url | config)`
- `java.put(...)`
- `java.base64Encode/Decode`
- `java.md5Encode`
- `java.sha1`
- `JSON.parse / JSON.stringify`
- `org.jsoup.Jsoup.parse(...).select(...).text()/html()/attr()`

### 渐进支持

暂列二阶段及以后：

- AES/DES 等更完整 crypto 行为
- 更复杂的 source variable / 登录态行为
- 极端复杂的 Java/Android 专属辅助接口

## 错误处理与回退

### 执行层级

1. **原生等价 fast-path**
   - 仅对确认等价的简单模式直接 Python 执行
2. **Node worker 原生模式主路径**
   - 承担大部分复杂真实书源 JS
3. **结构化失败返回**
   - 返回 error code、trace、compat diff，不再只给 `None`

### 错误码

至少区分：

- `JS_SYNTAX_ERROR`
- `JS_RUNTIME_ERROR`
- `JS_TIMEOUT`
- `WORKER_CRASHED`
- `BRIDGE_PROTOCOL_ERROR`
- `HTTP_BRIDGE_ERROR`
- `UNSUPPORTED_JAVA_API`
- `UNSUPPORTED_JSOUP_USAGE`
- `NATIVE_SEMANTICS_MISMATCH`

### worker 回退

- 进程崩溃：自动重启
- 单次执行超时：中断本次，必要时重建 worker
- 连续失败超阈值：标记 unhealthy 并切换新实例

### source 回退

- 某条 JS rule 失败时，当前 source 失败但服务不崩
- 上层多源互补继续工作
- diagnostics 中保留规则摘要、阶段、错误码、compat diff

### feature flags

建议增加：

- `LEGADO_JS_NATIVE_MODE_ENABLED`
- `LEGADO_JS_WORKER_ENABLED`
- `LEGADO_JS_HTTP_BRIDGE_ENABLED`
- `LEGADO_JS_TRACE_ENABLED`
- `LEGADO_JS_STRICT_COMPAT_MODE`

用于本地灰度启用与回退。

## 可观测性

每次执行记录 `JsExecutionTrace`，至少包括：

- source id / source name
- stage
- rule 摘要
- compat profile
- builtin 是否命中
- worker 执行耗时
- bridge HTTP 次数
- cache 写入 key
- 最终成功/失败
- 错误码
- compat diff

目标是让真实书源回归时能快速定位：

- 是 JS 语法问题
- 是 HTTP bridge 失败
- 是缓存未同步
- 是 Jsoup / crypto 兼容不足
- 还是与原生语义存在偏差

## 差异验证策略

为了接近“完美复刻”，必须引入**差异测试**，不能只靠普通单元测试。

### 差异基线

建立 `fixtures/legado_native_cases/` 或同类测试集，覆盖：

- `java.ajax` 直调
- `cache.putMemory/getFromMemory`
- `Jsoup.parse().select()`
- `searchUrl=@js:`
- `bookInfo.init`
- `tocUrl` 动态生成
- `content` 二次请求
- 列表 / 单值 / 字符串转换

### 验证方式

1. 记录原生 Legado 期望行为样本
2. 在服务端运行同一脚本和上下文
3. 对比：
   - 返回值
   - cache 变更
   - 请求次数/请求目标
   - 错误形态
4. 生成 `compat diff`

### 回归目标

不是“代码看起来像”，而是：

- 关键书源 case 的行为输出尽量一致
- 偏差被持续压缩
- 每次增强都能知道是否破坏了原生兼容

## 第一阶段实施范围

### P1

1. Node worker 长驻化
2. `@js:` `searchUrl` 真执行
3. `java.get/post/ajax` bridge
4. 统一 context/cache 同步
5. 结构化 trace / error code
6. 引入 `LegadoJsCompatProfile`
7. 建立最小差异测试集

### P2

8. `org.jsoup.Jsoup.parse(...).select(...)` 兼容层
9. `ruleBookInfo.init` / `tocUrl` / `ruleContent.content` 复杂 JS 强化
10. 真实书源 smoke 回归脚本扩展
11. compat diff 报告输出

### P3

12. crypto 扩展
13. 更多 Java API shim
14. source variable / 登录态增强
15. 更严格的原生行为回放与回归

## 测试策略

### 单元测试

新增重点：

- `tests/test_js_runtime_worker.py`
- `tests/test_js_http_bridge.py`
- `tests/test_jsoup_shim.py`
- `tests/test_search_url_js_execution.py`
- `tests/test_legado_native_semantics.py`
- `tests/test_legado_compat_diff.py`

覆盖：

- JS 返回字符串 / dict / list
- cache 写入回传
- `java.get/post/ajax`
- worker 超时 / 崩溃 / 重启
- 结构化错误码
- `searchUrl=@js:` 生成请求并成功搜索
- 原生语义关键行为是否一致

### 集成测试

扩展现有 fetcher/read service 测试：

- `search -> toc -> content`
- `init -> tocUrl -> chapterList`
- `content -> 二次请求 -> 正文返回`
- selector 与 JS 混合串联

### 真实书源 smoke

建立指定源回归集，优先选择：

1. 简单 HTML 源
2. JSON 源
3. `searchUrl=@js:` 源
4. `content` 二次请求源
5. `Jsoup.parse` 源
6. `cache.putMemory` 源
7. crypto/token 源

固定回归关键词：

- `捞尸人`
- `斗罗大陆`

同时新增“原生差异观察项”：

- 结果是否一致
- cache 行为是否一致
- 请求链是否一致
- 错误形态是否一致

## 成功标准

第一阶段完成后至少满足：

1. 已跑通的 `source 7 / 33` 不回退
2. 一部分此前被跳过的纯 JS 搜索源能返回真实结果
3. trace 能完整呈现 JS 执行链
4. 失败源有明确错误分类，而不是 silent fail
5. pytest、smoke、真实搜索脚本可重复运行
6. 建立一套可持续的“与 Legado 原生对照”的 compatibility baseline
7. 服务端增强默认不破坏原生书源行为

## 风险与对策

### 风险 1：Node worker 协议复杂度上升

对策：

- 协议先控制在最小集合
- 仅支持 execute / bridge call / trace / result 几类消息
- 用模型类做协议校验

### 风险 2：真实书源差异远超预期

对策：

- 先做 P1/P2 高频能力
- 保留 feature flag
- 用真实源回归集迭代补兼容
- 用 compat diff 确认差异是否收敛

### 风险 3：引擎增强影响现有稳定源

对策：

- fast-path 仅限已确认等价模式
- source 7 / 33 设为回归基线
- 所有变更都走 pytest + smoke + 真实书源测试

### 风险 4：宣称“完美复刻”但缺少客观验证

对策：

- 把“完美复刻”落地为行为级 compatibility baseline
- 以差异测试而非主观判断作为验收标准
- 对未覆盖行为明确标识，不做含糊承诺

## 实施边界

- 本地开发
- 不走 Docker
- 使用本机 Python 3.13
- 本机 SQLite DB
- 沿用 `app/application/services/*` 与 `app/interfaces/http/*` 主线
- 不回退旧 `app/api/routers/*`
- 仓库当前无 `.git`，因此本次只写入 spec 文件，不执行 commit
