# 2026-07-09 JS engine follow-up round 2

## 本轮新增能力

- `searchUrl @js` 支持直接返回：
  - 纯 URL 字符串
  - `URL + JSON.stringify(option)` 请求串
  - 相对路径 + JSON 请求串
- JS worker 支持：
  - 顶层变量别名：`key / searchKey / page`
  - `source.get / source.put / source.getKey / source.getVariable / source.getLoginInfoMap`
  - `getHost / urlIP / cookie.removeCookie`
  - `java.put / java.get(非URL内存读取) / java.getString`
  - `java.log / java.longToast / java.encodeURI / java.androidId`
  - `java.get/post/ajax` 响应包装器的字符串方法：
    - `match / replace / includes / split / trim / substring / indexOf`
  - 返回字符串中的表达式模板二次展开：
    - `{{java.encodeURI(key)}}`
    - `{{(page-1)*10+1}}`
- `JsWorkerClient` 支持对 `BeautifulSoup Tag` 上下文做安全序列化
- `smoke_js_compat_sources.py` 增强为显示：
  - `exec=ok/fail`
  - `preview=...`
  - `hits=...`

## 已验证

### pytest

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_legado_native_semantics.py tests\test_legado_compat_diff.py tests\test_js_runtime_worker.py tests\test_js_http_bridge.py tests\test_jsoup_shim.py tests\test_search_url_js_execution.py tests\test_legado_engine_compatibility.py tests\test_source_read_service.py tests\test_source_complement_app_service.py tests\test_character_calibration_service.py tests\test_source_import_main_api.py tests\test_api_sources_main.py tests\test_api_modules_main.py -q
```

结果：

- `47 passed`

### 真实非 JS 基线

```powershell
.\.venv\Scripts\python.exe scripts\search_real_books.py
```

结果：

- `source_id=7 / 12 / 33` 不回退
- `捞尸人 / 斗罗大陆` 搜索结果保持正常

### 真实 JS smoke

```powershell
.\.venv\Scripts\python.exe scripts\smoke_js_compat_sources.py
```

结果摘要：

- 前 10 个 `@js:` 搜索源中：
  - `exec=ok` 的源显著增多
  - 但 `hits` 仍为 `0`
- 典型剩余问题：
  - 登录/token 依赖：`source_id=4`
  - 上游连接/重定向站点行为：`source_id=30`
  - 站点返回 HTML 而非原预期 JSON：`source_id=109`
  - 源自定义 helper 未实现：`source_id=50 (urlSearchSeries)`

## 结论

本轮已经把 **“JS 能否执行”** 大幅推进到 **“大量真实源的 JS searchUrl 已能正常产出 request/url”**。

当前主阻塞已经从：

- 缺 JS 运行语义

转变为：

- 上游站点可达性 / WAF / token / 站点特定 helper

这意味着后续工作应进入 **按源逐个攻克** 阶段。
