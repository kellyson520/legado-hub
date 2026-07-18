# LegadoHub Pro 代码指南

更新时间：2026-07-19

架构总览见 [`ARCHITECTURE.md`](ARCHITECTURE.md)，当前运行基线见 [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md)。本指南只保留会影响新增代码的规则，旧实现说明不再作为入口。

## 目录职责

```text
backend/app/
├── core/                         # 日志、异常、响应、分页、安全、脱敏、策略
├── domain/
│   ├── entities/                 # 实体、值对象、领域事件
│   ├── repositories/             # 仓储抽象
│   └── services/                 # 不依赖框架的领域规则
├── application/
│   ├── ports/                    # 外部能力协议
│   └── services/                 # 用例编排与事务边界
├── infrastructure/
│   ├── persistence/              # SQLite 会话、ORM、仓储实现、组合根
│   ├── http/                     # 安全 HTTP 出站适配器
│   ├── legado/                   # Legado 规则/JS/原生运行时
│   ├── crawler/                  # 源抓取与页面解析
│   └── browser/                  # Playwright/浏览器适配器
├── interfaces/http/              # FastAPI 路由、认证、响应映射
└── tasks/                        # 调度适配器

frontend/src/
├── api/                          # 唯一 API 客户端与领域 API 模块
├── features/                     # 按界限上下文组织的页面
├── components/                   # 共享布局、表格、状态和分页组件
└── hooks/                        # 共享交互与服务端分页
```

`app.services` 是历史兼容命名空间，不属于运行入口；新代码不得导入它。`app.database` 和 `app.core.compatibility` 也只是兼容门面。

## 依赖规则

依赖只能沿以下方向流动：

```text
interfaces -> application -> domain
       |          |           ^
       |          +-> ports   |
       +-> composition root -+-> infrastructure
core 被各层使用；领域事件定义在 domain，事件总线只负责投递。
```

- `domain` 只能使用标准库和自身模块；不能导入 `app.core`、`app.application`、`app.infrastructure`、FastAPI、ORM 或网络客户端。
- `application` 不能导入 ORM、HTTP 客户端或旧 `app.services`；跨边界能力通过 `application/ports` 注入。
- `infrastructure` 实现领域仓储和应用端口；除组合根外不得反向导入应用服务。浏览器适配器只依赖端口类型。
- `interfaces/http` 不创建数据库会话、不实例化 ORM/HTTP client，统一调用命名工厂得到的应用服务。
- `tasks` 只负责调度、日志上下文和异常隔离；任何数据变更都通过应用服务。

架构边界由 `backend/tests/test_dependency_direction.py` 持续验证。

## 统一能力

日志：

```python
from app.core.logging import get_logger

logger = get_logger("source.read")
logger.info("source read completed", extra={"action": "source_read", "count": 3})
```

禁止直接调用 `logging.getLogger`、`print` 记录运行日志，敏感信息必须经过 `app.core.redaction`。

异常和响应：

```python
from app.core.exceptions import NotFoundException, ValidationException
from app.core.response import from_paginated_result, ok

raise NotFoundException("source not found")
return ok(data=payload, message="source loaded", meta={})
```

路由不得返回未包装的业务对象；分页使用 `app.core.pagination`，前端使用 `useServerPagination`。

出站 HTTP：

- 应用层只声明/使用 `application.ports.http`。
- 具体请求使用 `app.infrastructure.http` 或 Legado 运行时客户端。
- `app.core.url_safety` 统一校验 URL、DNS 结果、重定向和跨源凭据裁剪。
- 禁止在新代码中使用 `ssl=False`、裸 `aiohttp`/`httpx` 请求或绕过安全客户端。

模型供应商：

- `application.ports.provider` 是模型协议和路由组常量。
- `ProviderPlatformService` 负责重试、降级、配额范围和错误脱敏。
- 具体 OpenAI-compatible 客户端只位于 `infrastructure/providers`。

事件：

- 事件载荷定义在 `domain/events.py`。
- `core.events` 只提供进程内总线和兼容导出。
- 领域服务通过回调/端口发布事件，不直接导入日志或总线实现。

## 新功能流程

1. 定义领域实体、值对象、不变量和仓储/领域事件。
2. 为网络、模型、浏览器、缓存或文件能力添加 `application/ports` 协议。
3. 在 `application/services` 编排用例，显式接收仓储和端口依赖。
4. 在 `infrastructure` 实现协议，并在 `app.infrastructure.persistence.factory` 组装。
5. 在 `interfaces/http` 添加薄路由和权限声明。
6. 同时添加领域、应用、基础设施、HTTP contract 和依赖方向测试。

不要新增第二套日志、分页、响应 envelope、API 客户端、数据库会话、事件总线或书源解析入口。

## 前端规则

- 页面只调用 `frontend/src/api/modules/*`，不直接使用 `fetch`、Axios 或拼接 `/api` 前缀。
- 所有普通请求和流式请求都通过 `api/client.ts`，认证刷新由客户端统一处理。
- 页面按 feature 拆分；表格、筛选、状态、分页和布局优先复用 `components/`。
- 组件不保存后端 ORM/供应商模型，API 模块负责 snake_case 到页面模型的边界转换。

## 验证命令

```bash
cd backend
../backend/.venv-linux/bin/pytest -q
python3 -m compileall -q app tests

cd ../frontend
npm run test -- --run
npm run build
```

提交前还要运行 `git diff --check`，并确认 `git status` 中没有构建缓存或本地数据库文件。
