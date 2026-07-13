# 后端测试契约迁移（第二批）设计

## 目标

将缓存测试基础设施、异常处理测试和响应构造测试迁移到当前后端架构的公开契约，并修复 `from_exception()` 与 `AppException` 的字段不一致问题。

## 当前契约

- `app.core.exceptions.AppException` 使用 `code`、`message`、`status_code` 和 `details`。
- 具体异常为 `AuthenticationException`、`AuthorizationException`、`ValidationException`、`NotFoundException`、`ConflictException` 和 `ExternalServiceException`。
- `app.core.exception_handlers` 负责注册和实现 FastAPI 异常处理器。
- `app.core.response.from_exception()` 必须优先读取当前异常的 `code`，并保留对历史 `error_code` 属性的回退兼容。

## 变更范围

1. 保留已补充的 `cache_provider` fixture，使 `MemoryCacheProvider` 测试可独立运行。
2. 重写 `test_core_exceptions.py`，断言当前异常类及其 HTTP handler 的真实行为。
3. 更新 `test_core_response.py`，以当前 `AppException.code` 和历史 `error_code` 回退为契约。
4. 仅对 `response.py` 作一个最小生产修复：`code` 优先、`error_code` 次之、`INTERNAL_ERROR` 兜底。

## 非目标

- 不恢复已删除的 `BaseAppException`、`QuotaExceededException` 或 `app.routers`。
- 不更改既有 HTTP 状态码、英文默认提示、异常 handler 的响应 envelope。
- 不扩展异常层级或改造全局异常处理机制。

## 验收

以下命令必须通过：

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q tests\test_infra_cache.py tests\test_core_exceptions.py tests\test_core_response.py --tb=short
```

并在提交前通过：

```powershell
git diff --check
```
