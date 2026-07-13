# 2026-07-09 source health follow-up round 2

## 本轮继续内容

- 增强 `SourceProbeService`：对 `@js:` 搜索源增加 search preflight
  - 记录 `request_preview`
  - 记录 `js_exec_status`
  - 记录 `js_error`
- 增强 `SourceHealthClassifierService`
  - 识别 `token=undefined`
  - 识别 `_token=null`
  - 识别 `is not defined`
  - 识别 `Unexpected token '<'`
  - 修正空 detail 被误判成 `unknown_error` 的问题
- 修复 source health 脚本/接口的资源释放
- 修复 probe 历史 JSON 序列化，对复杂对象使用 `default=str`

## 新增测试

- `test_probe_service_collects_js_preflight_request_preview`
- `test_classifier_marks_helper_missing_as_dead`

## 验证

### pytest

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_source_health_repo.py tests\test_source_probe_service.py tests\test_source_health_classifier_service.py tests\test_source_health_admin_service.py tests\test_source_routing_service.py tests\test_api_source_health.py tests\test_source_health_scheduler.py tests\test_source_read_service.py tests\test_source_complement_app_service.py tests\test_character_calibration_service.py tests\test_source_import_main_api.py tests\test_api_sources_main.py tests\test_api_modules_main.py tests\test_legado_native_semantics.py tests\test_legado_compat_diff.py tests\test_js_runtime_worker.py tests\test_js_http_bridge.py tests\test_jsoup_shim.py tests\test_search_url_js_execution.py tests\test_legado_engine_compatibility.py -q
```

结果：
- `62 passed`

### 真实探测

```powershell
.\.venv\Scripts\python.exe scripts\probe_source_health.py --source-ids 4 23 50 109 --keywords 捞尸人 斗罗大陆
```

结果：
- `source_id=4` -> `blocked / token_missing`
- `source_id=23` -> `blocked / token_missing`
- `source_id=50` -> `dead / helper_missing`
- `source_id=109` -> `dead / upstream_changed`

### 真实搜索回归

```powershell
.\.venv\Scripts\python.exe scripts\search_real_books.py
```

结果：
- `source_id=33` 维持 `healthy`
- `source_id=7` 当前被识别为 `degraded / parse_empty`
- 搜索链路未回退，`捞尸人 / 斗罗大陆` 仍可正常出结果

### JS smoke

```powershell
.\.venv\Scripts\python.exe scripts\smoke_js_compat_sources.py
```

结果摘要：
- `source_id=4` -> `blocked / token_missing`
- `source_id=23` -> `blocked / token_missing`
- `source_id=50` -> `dead / helper_missing`
- `source_id=109` -> `dead / upstream_changed`
- `source_id=30 / 67 / 108` 等仍是 `unknown_error`

## 结论

本轮已把一批原先笼统的 `unknown_error` 收敛为可操作原因：

- token 缺失
- helper 缺失
- 上游改版

下一阶段应继续处理：

- `source_id=30 / 67 / 108` 等 `unknown_error` 的 HTTP / WAF / parse 细分
- 后台详情页展示最近 probe 历史与 request preview
- 定时调度批量探测与自动恢复策略落地
