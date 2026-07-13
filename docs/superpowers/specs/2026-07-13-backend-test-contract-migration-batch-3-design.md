# 后端测试契约迁移（第三批）设计

## 目标

将已经指向删除架构的应用服务测试迁移到当前 `AuthAppService` 和
`SourceAppService` 的公开契约，并补齐领域实体测试实际需要的三组测试数据
fixture。

## 根因

`backend/tests/test_app_services.py` 仍依赖旧的 `UserRepository`、旧领域
实体及已移除的服务方法；其 `MockSourceRepository` 还继承当前抽象仓储却未
实现全部抽象方法。因此测试在收集或执行阶段失败，且不能反映当前服务的行为。

`test_domain_entities.py` 的三个失败只由缺失的测试数据 fixture 引起，领域实体
本身的契约仍然有效。

## 方案

采用普通的异步内存 fake（duck-typed repository），而不继承抽象仓储：

- `FakeAuthRepository` 只实现当前认证服务在测试场景中调用的方法，并保存用户、
  RefreshSession、API key 与审计事件的真实领域实体。
- `FakeSourceRepository` 只实现当前书源服务的 CRUD、分页、导出和导入去重路径。
- 测试直接调用当前应用服务的公开方法，验证返回值、领域异常和可观测副作用，
  不恢复已删除的 API，也不测试 fake 自身的实现细节。
- 在 `conftest.py` 统一提供当前 `BookSource`、`RssSource` 和
  `Subscription` 所需的完整最小 fixture。

## 覆盖范围

认证服务：

- 管理员创建用户、重复用户名和不支持角色；
- 用户列表序列化；
- 最后一个启用管理员不能被禁用；
- 禁用用户撤销 refresh session；
- 创建、启停、删除 API key 并记录审计事件；
- 登录成功、错误凭据拒绝及登出。

书源服务：

- 分页列表、创建、更新、删除；
- 导出计数；
- 从 UTF-8 JSON 文件导入，并在 `replace_existing=False` 时按
  `bookSourceUrl` 过滤已有书源。

领域实体：

- `BookSource.from_dict`、`RssSource.from_dict` 与 `Subscription` 构造所需
  的 fixture 可独立运行。

## 非目标

- 不恢复 `BaseAppException`、`QuotaExceededException`、`app.routers`、
  旧 `UserRepository`、旧 domain entity 或匿名旧 API。
- 不修改当前应用服务的生产行为。
- 不处理本批之外的 scheduler、安全辅助函数、旧匿名 HTTP API 测试。

## 验收

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q tests\test_app_services.py tests\test_domain_entities.py --tb=short
```

提交前还必须执行：

```powershell
git diff --check
```
