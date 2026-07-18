# LegadoHub Pro 架构

更新时间：2026-07-19

本文件是运行架构的入口。历史方案保存在 `docs/superpowers/`，不代表仍然存在的代码入口。

## 分层

```text
interfaces/http -> application/services -> domain
       |                  |                |
       |                  +-> application/ports
       |                                   |
       +-------------------------- composition root
                                      infrastructure

core: transport-neutral cross-cutting policies used by every layer
```

- `domain` 只包含实体、值对象、领域服务、领域事件和仓储契约；不得依赖 FastAPI、ORM、网络客户端、应用层或基础设施。
- `application` 只编排用例，依赖领域契约、`application/ports` 和 `core`。具体数据库、HTTP、浏览器、模型供应商由组合根注入。
- `infrastructure` 实现仓储和出站端口，包括 SQLite、Legado 运行时、安全 HTTP、浏览器和模型供应商。
- `interfaces/http` 只负责请求校验、认证/权限依赖、应用服务调用和统一响应映射，不打开数据库会话。
- `tasks` 是调度适配器；持久化变更必须调用应用服务，不能直接操作 SQLAlchemy 模型。
- `core` 提供日志、异常、响应 envelope、分页、认证安全、URL 安全、脱敏和事件总线。领域事件定义位于 `domain/events.py`，事件总线只负责传输。

架构测试位于 `backend/tests/test_dependency_direction.py`，会检查领域纯度、应用层基础设施隔离、统一日志和任务适配器边界。

## 组合根

`app.infrastructure.persistence.factory` 是唯一的运行时组合根：它创建仓储、端口适配器和应用服务。路由、任务和生命周期只调用命名工厂，不在局部重新配置数据库或 HTTP 客户端。

统一出站 HTTP 由 `app.infrastructure.http` 提供，所有公开 URL、DNS 解析、重定向和敏感请求头都经过 `app.core.url_safety`。Legado 阅读、页面工具、健康探针和 webhook 共享这条安全策略。

## 前端边界

前端只依赖 `frontend/src/api/client.ts` 和 `frontend/src/api/modules/*`。Axios 请求、认证刷新、统一 envelope 解包和流式事件请求都在 API 客户端完成；页面组件不拼接后端实现细节，不直接操作数据库或服务端模型。

页面按 `features/<bounded-context>` 组织，通用布局、状态、表格、筛选和分页组件位于 `components/`，统一分页请求位于 `hooks/useServerPagination.ts`。

## 扩展规则

新增能力按以下顺序实现：

1. 在 `domain` 定义不变量、实体/值对象、事件和仓储契约。
2. 在 `application/ports` 声明网络、模型、文件或缓存能力，在 `application/services` 编排用例。
3. 在 `infrastructure` 实现端口，并在组合根注入。
4. 在 `interfaces/http` 暴露薄路由和权限声明。
5. 添加领域、应用、适配器、HTTP contract 和依赖方向测试。

不要新增第二套日志、分页、响应 envelope、API 客户端、数据库会话或源解析入口；兼容模块只能转发到当前实现，不能重新实现业务逻辑。
