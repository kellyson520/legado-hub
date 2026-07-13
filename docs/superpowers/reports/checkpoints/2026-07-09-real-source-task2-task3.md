# 2026-07-09 real-source task2/task3 checkpoint

## 完成项

- 修复 `app.infrastructure.legado.engine` compatibility：
  - `JsonPathExt`
  - `RuleSelector / RuleType / SelectorResult`
  - `JsRuntime` Node/cache 兼容
  - `LegadoHttpClient` 延迟创建 `CookieJar`
- 打通真实链路：
  - `scripts/import_share_book_sources.py`
  - `scripts/search_real_books.py`
  - `source 7` 可真实 `search / toc / content`
  - `source 33` 可真实 `search / toc / content`
- 新增多源显式互补服务：
  - `SourceComplementAppService`
  - `POST /api/reading/complement`
  - `scripts/smoke_source_complement.py`
- 新增搜索质量选择：
  - `SourceReadService.search_books(..., author_hint=...)`
- 新增人物校准基础能力：
  - `CharacterCalibrationService`
  - `POST /api/reading/characters/calibrate`
  - `scripts/smoke_character_calibration.py`

## 本地验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_character_calibration_service.py tests\test_source_read_service.py tests\test_source_complement_app_service.py tests\test_legado_engine_compatibility.py tests\test_engine_selector_pipeline.py tests\test_source_import_main_api.py tests\test_api_sources_main.py tests\test_api_modules_main.py -q

.\.venv\Scripts\python.exe scripts\import_share_book_sources.py
.\.venv\Scripts\python.exe scripts\search_real_books.py
.\.venv\Scripts\python.exe scripts\smoke_source_complement.py
.\.venv\Scripts\python.exe scripts\smoke_character_calibration.py
```

## 结果摘要

- `shareBookSource.json` 成功导入：`2385`
- 真实搜索：
  - `捞尸人`
  - `斗罗大陆`
- 真实目录/正文：
  - `source_id=7`
  - `source_id=33`
- 多源互补 smoke：
  - 输入 `2` 源
  - 成功源 `2`
  - 最终优选源 `https://novel.cooks.tw`
- 人物校准 smoke：
  - `source_id=7` 与 `source_id=33` 的 `捞尸人` 人物集合无交集
  - `overlap_score = 0.0`
