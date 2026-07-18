# 当前架构基线

更新时间：2026-07-19

这份文档描述仓库当前实际运行的架构。早期设计文档中的旧路由树和兼容代码只作为历史记录，不是可继续扩展的运行入口。

## 运行边界

FastAPI 只从 `app.main` 挂载 `app.interfaces.http.router.api_router`。后台资源统一使用 `/api/*`，响应、异常、认证、权限和审计由同一套核心组件处理。`app/api/routers`、`app/routers` 和 `app/interfaces/api` 已从源码树退役。

## 依赖方向

```text
interfaces/http
       |
       v
application/services -----> application/ports
       |                         ^
       v                         |
domain/entities + repositories  |
       ^                         |
       +---- infrastructure -----+

core (logging, response, exceptions, security, URL safety, redaction)
      is shared by every layer and imports no application implementation.
```

硬性规则：

- `domain` 只依赖标准库；仓储、外部模型和网络能力必须是抽象接口。
- `application` 只能依赖 `domain`、`core` 和 `application.ports`，不能导入 ORM、HTTP 客户端或 `app.services`。
- `infrastructure` 实现 domain 仓储和 application ports；组合工厂集中在 `app.infrastructure.persistence.factory`。
- `interfaces` 只做请求校验、权限依赖和响应映射，不访问数据库会话。
- 所有非 `core` 模块通过 `app.core.logging.get_logger` 获取结构化日志记录器。

`backend/tests/test_dependency_direction.py` 会在测试中扫描这些规则，防止新代码重新引入反向依赖。

## 统一基础设施

- SQLite 会话、`Base` 和 `engine` 的唯一实现是 `app.infrastructure.persistence.sqlite.session`。
- `app.database` 仅是旧导入路径的兼容门面，新代码不得依赖它。
- URL 出站策略位于 `app.core.url_safety`，联合测试、页面探针和 Legado HTTP 客户端共享它；DNS 解析结果如果指向私有地址会被拒绝。
- Agent 结果和异常跨越模型、对话或持久化边界前必须通过 `app.core.redaction.sanitize_for_boundary`。
- 分页、响应 envelope、异常处理、认证上下文和事件总线均由 `app.core` 提供，业务模块不重新实现。

## 源阅读与联合测试

正式书源规则写入 `source_versions`，只有审核流水线可以发布。`source.joint_test` 使用 `ephemeral_book_sources` 临时表：记录带租户范围和 15 分钟过期时间，阅读服务必须携带租户范围；测试完成后主动清理，过期时间作为兜底。联合测试不会写入全局 `book_sources`，也不会改变发布状态。

源导入解析通过 `application.ports.SourceImportParser` 注入。当前实现位于 `app.infrastructure.crawler.source_fetcher`，旧的 `app.services.fetcher` 仅保留兼容导出。

## 组合与扩展

新增领域能力时按以下顺序落盘：

1. 在 `domain/entities` 定义状态和不变量，在 `domain/repositories` 定义持久化契约。
2. 在 `application/services` 编排用例，在 `application/ports` 声明网络、模型或文件系统能力。
3. 在 `infrastructure` 实现端口，并只在组合工厂注入具体实现。
4. 在 `interfaces/http` 添加薄路由和权限声明。
5. 为依赖方向、应用用例、基础设施实现和 HTTP contract 分层添加测试。

不要在路由中实例化 ORM、HTTP client 或 Provider；不要把业务规则放回 `core`；不要新增第二套 API client、分页或日志封装。
