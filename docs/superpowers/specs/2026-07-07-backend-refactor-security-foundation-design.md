# LegadoHub 后端重构与安全基线设计

> 设计日期：2026-07-07  
> 工作目录：`C:\Users\lihuo\Desktop\legado-hub`  
> 子项目：1 / 4（后端修复与安全基线）  
> 当前工作副本无 `.git`，因此本次只能落盘 spec，无法执行 git commit。

---

## 1. 目标

本阶段要把 LegadoHub 后端从“多套并行 API + 旧运行面 + 混合鉴权/数据模型”的状态，重构成一套可长期演进的新主干后端。

完成后应达到：

- 运行时只保留一套新的主 API
- 删除旧 v0 运行面，不做兼容保留
- 允许 SQLite schema 破坏式重建，以清库重建为默认路径
- 后台采用 `Access Token + Refresh Token`
- 引入完整细粒度 RBAC
- 所有后台接口统一鉴权、统一错误模型、统一审计
- `sources / engine / dashboard / export / health / ai / translation / novel / system` 全部挂到同一主干
- 本机 Python 3.13 + SQLite 可稳定运行

---

## 2. 设计前提与已确认决策

本设计基于以下已确认决策：

1. 本阶段只做子项目 1：后端修复与安全基线
2. 重构强度为深度重构
3. 采用“新主 API”而不是继续沿用 v0 或 v1
4. 最终 **不保留 v0**，旧 API 直接退出运行面
5. 公开接口只保留 `/api/status`
6. 导出接口也必须鉴权
7. 后台登录模型采用 `Access Token + Refresh Token`
8. 权限模型采用完整细粒度 RBAC
9. 权限资源范围覆盖后台核心域 + AI / translation / novel 扩展域
10. 扩展域不是只接骨架，而是第一阶段一起修到“稳定可控”
11. SQLite schema 允许直接重做，不做旧数据迁移
12. 旧数据、旧 API 都允许破坏性重做

---

## 3. 范围

### 3.1 In Scope

- 新主干后端入口与路由树
- 新认证体系
- 新 RBAC 模型
- 新 SQLite schema
- 新统一响应/异常/审计模型
- 新 sources / subscriptions / filters / export / dashboard / health 主链路
- 新 engine 主链路
- AI / translation / novel 域接入同一主干并修到稳定可控
- Python 3.13 本机运行与构建可重复性

### 3.2 Out of Scope

- 旧数据迁移
- v0 / v1 兼容保留
- Docker 优先的生产编排优化
- 多数据库适配
- 面向第三方调用者的旧 API 平滑迁移层
- 前端后台管理面板的大规模 UI 重构（这是后续子项目 3）

---

## 4. 当前问题摘要

当前工作副本存在以下核心问题：

### 4.1 API 与运行面混乱

- `backend/app/main.py` 只挂载 v0 路由
- 文档仍宣称有 v1 Pro API
- 仓库里同时存在：
  - `app/interfaces/api`
  - `app/api/routers`
  - `app/routers`

这导致“哪套接口是权威实现”长期不清晰。

### 4.2 安全模型不成立

- v0 关键写接口未鉴权
- `SECRET_KEY` 有硬编码默认值
- 密码哈希仍是自定义 `SHA256 + SECRET_KEY`
- CORS 过宽
- 权限模型不完整且运行面未真正统一

### 4.3 数据模型与接口契约漂移

- 前后端参数命名不一致（camelCase / snake_case）
- 分页响应不一致
- dashboard 聚合逻辑错误
- groups 数据链路实际缺失

### 4.4 规则引擎与扩展域接入松散

- `compatibility.py`、`rule_selector.py`、`generator.py`、`book_searcher.py`、crawler/fetcher 中存在重叠职责
- evaluate / repair / generate / test 没有共用同一套规则规范和结果模型
- AI / translation / novel 也未统一到同一认证、权限、任务、错误模型

### 4.5 工程基础设施不可复制

- `requirements.txt` 不能在本机 Python 3.13 干净跑通
- SQLite 默认路径偏 Docker 场景
- 运行时路径有容器硬编码

---

## 5. 总体方案

本阶段采用 **“直接建立新主干后端，旧实现退出运行面”** 的方案。

这意味着：

- 运行时只保留新主 API
- 旧 API 不再挂载
- 旧 schema 不保留
- 旧服务层、旧 router 树、旧 auth 路径只作为迁移参考
- 后续会逐步清理旧文件，但第一步先以“新主线可运行”为目标

这是当前约束下成本最低、边界最干净的方案。

---

## 6. 目标架构

### 6.1 运行时边界

运行时仅保留：

- 一套新的 `main.py` 应用入口
- 一套新的主 API 路由树
- 一套新的应用服务层
- 一套新的持久化、鉴权、权限、审计、任务与规则基础设施

不再把以下内容作为运行主线：

- 旧 v0 兼容 API
- 旧 v1 入口
- `app/api/routers`
- `app/routers`
- 旧“半 DDD、半直连 ORM”的混合调用路径

### 6.2 分层

#### API Layer

提供统一资源入口：

- `/api/status`
- `/api/auth/*`
- `/api/admin/users/*`
- `/api/admin/roles/*`
- `/api/admin/permissions/*`
- `/api/admin/api-keys/*`
- `/api/admin/audit/*`
- `/api/admin/sessions/*`
- `/api/sources/*`
- `/api/subscriptions/*`
- `/api/filters/*`
- `/api/engine/*`
- `/api/dashboard/*`
- `/api/health/*`
- `/api/export/*`
- `/api/ai/*`
- `/api/translation/*`
- `/api/novel/*`
- `/api/system/*`

#### Application Layer

职责：

- 编排用例
- 处理事务边界
- 调用仓储与基础设施
- 执行权限守卫、审计记录、任务调度

约束：

- 不直接暴露 ORM
- 不直接散落鉴权逻辑
- 不直接手写 HTTP 响应结构

#### Domain Layer

核心实体至少包括：

- User
- Role
- Permission
- ApiKey
- RefreshSession / RefreshToken
- BookSource
- RssSource
- Subscription
- FilterRule
- EngineJob / EngineEvaluation / EngineRepair
- TranslationJob / TranslationChunk / TranslationDictionary
- Novel / NovelIngestion / NovelTask / NovelAnalysis
- AITask / AICharacterResult / AIWorldResult / AIStorylineResult

#### Infrastructure Layer

提供：

- SQLite 持久化
- Token 签发与刷新
- 密码哈希
- Redis 缓存 / 限流 / 队列（可降级）
- 调度器
- 规则引擎执行器
- 审计日志
- 配置加载

---

## 7. 新主 API 规范

### 7.1 API 命名

统一使用一套新主 API，不再出现：

- `/api/v1/*`
- 旧 v0 命名面
- 并行旧 router 树命名

### 7.2 查询参数规范

统一采用 `snake_case`：

- `page`
- `page_size`
- `enabled_only`
- `source_type`
- `created_after`
- `sort_by`

### 7.3 响应契约

统一响应形状：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {},
  "meta": {},
  "trace_id": "..."
}
```

分页统一放在 `meta`：

```json
{
  "page": 1,
  "page_size": 20,
  "total": 100,
  "total_pages": 5
}
```

### 7.4 错误模型

统一输出结构化错误：

- `AUTHENTICATION_ERROR`
- `AUTHORIZATION_ERROR`
- `VALIDATION_ERROR`
- `NOT_FOUND`
- `CONFLICT`
- `RATE_LIMITED`
- `QUOTA_EXCEEDED`
- `ENGINE_EXECUTION_ERROR`
- `RULE_VALIDATION_ERROR`
- `TASK_ERROR`
- `INTERNAL_ERROR`

并带：

- `message`
- `details`
- `trace_id`

---

## 8. 认证、会话与安全模型

### 8.1 认证方式

后台采用三种凭证，但用途分离：

#### Access Token

- 用于后台管理面板访问主 API
- 生命周期较短
- Bearer Token

#### Refresh Token

- 仅用于换发新的 access token
- 生命周期较长
- 必须存库
- 必须支持吊销

#### API Key

- 仅用于程序化访问与集成
- 不替代后台登录
- 独立权限、独立配额、独立审计

### 8.2 公开面

仅保留：

- `GET /api/status`

其余接口默认鉴权，包括：

- export
- health
- engine
- dashboard
- AI
- translation
- novel

### 8.3 密码与密钥

- 删除 `SHA256 + SECRET_KEY` 密码哈希
- 改为 **bcrypt**（首选）或 argon2
- `SECRET_KEY` 不允许使用硬编码默认生产值
- 启动阶段校验关键安全配置
- 开发环境可自动生成临时 secret，但必须显式记录在启动日志中

### 8.4 Session 管理能力

必须支持：

- 登录
- 刷新 access token
- 当前会话登出
- 全部会话登出
- 管理员吊销他人会话
- API Key 启用 / 禁用 / 删除

### 8.5 审计

必须审计：

- 登录成功 / 失败
- refresh
- logout
- 用户、角色、权限变更
- API Key 创建 / 禁用 / 删除
- 书源写操作
- engine generate / repair / evaluate / test
- health 批量检查
- export
- AI / translation / novel 的执行型操作

---

## 9. RBAC 设计

### 9.1 资源模型

RBAC 使用：

- users
- roles
- permissions
- user_roles
- role_permissions

### 9.2 权限粒度

权限采用：

- `resource.action`

例如：

- `users.read`
- `users.create`
- `users.update`
- `users.delete`
- `roles.assign`
- `book_sources.read`
- `book_sources.write`
- `engine.generate`
- `engine.evaluate`
- `engine.repair`
- `engine.test`
- `dashboard.read`
- `health.check`
- `export.read`
- `ai.run`
- `translation.run`
- `novel.manage`
- `system.audit.read`
- `system.jobs.manage`

### 9.3 覆盖范围

第一阶段权限资源范围覆盖：

- 后台核心资源
- sources / rss / subscriptions / filters
- engine
- dashboard / health / export / system
- AI
- translation
- novel

### 9.4 设计约束

- 第一阶段先完成完整 RBAC
- 不做更复杂的 ABAC / resource ownership 扩展
- 但模型需要为后续更细粒度授权留扩展位

---

## 10. 数据库 schema 重建方向

### 10.1 认证与权限

- `users`
- `roles`
- `permissions`
- `user_roles`
- `role_permissions`
- `refresh_tokens`
- `api_keys`
- `api_key_permissions`
- `audit_logs`

### 10.2 源管理

- `book_sources`
- `rss_sources`
- `subscriptions`
- `filter_rules`
- `source_health_logs`

### 10.3 规则引擎与写源

- `engine_jobs`
- `engine_evaluations`
- `engine_repairs`
- `rule_test_runs`（可选，如果实现在线规则测试记录）

### 10.4 扩展域

- `translation_jobs`
- `translation_chunks`
- `translation_dictionaries`
- `novels`
- `novel_ingestions`
- `novel_tasks`
- `novel_analysis_results`
- `ai_tasks`
- `ai_characters`
- `ai_worlds`
- `ai_storylines`

### 10.5 系统基础设施

- `quota_usage`
- `task_runs`
- `system_settings`

### 10.6 通用字段策略

能统一的资源应尽量带：

- `id`
- `status`
- `created_at`
- `updated_at`
- `created_by`
- `updated_by`

---

## 11. 规则引擎子系统设计

### 11.1 目标

把现在分散在：

- `compatibility.py`
- `rule_selector.py`
- `jsonpath_ext.py`
- `generator.py`
- `book_searcher.py`
- crawler/fetcher 中的部分逻辑

的规则能力，收敛成一个明确子系统。

### 11.2 子系统职责

- rule parsing
- rule execution
- rule normalization
- rule validation
- rule evaluation
- rule repair
- rule generation
- rule test harness

### 11.3 主流程

1. source input normalization
2. rule parsing
3. rule execution
4. rule validation
5. rule evaluation
6. rule repair
7. rule generation
8. rule test harness

### 11.4 设计原则

- HTML / JSON / text 规则执行结果必须统一
- evaluate / repair / generate 共用同一规则规范
- JSONPath / CSS / XPath / JS 不得各自漂移
- JS 规则执行必须有边界与结构化错误
- 所有失败必须输出结构化 diagnostics

### 11.5 与主系统的关系

规则引擎不再是“工具函数散落调用”，而是：

- 由 application service 驱动
- 由 engine API 统一暴露能力
- 由 audit / task / permission 模型统一约束

---

## 12. 扩展域接入策略

### 12.1 AI

AI 域必须接入：

- 新认证
- 新 RBAC
- 新错误模型
- 新审计
- 新任务模型
- 新配置模型

目标不是“先占位”，而是达到稳定可控。

### 12.2 Translation

translation 域必须：

- 统一 job / chunk / retry / status 模型
- 接入审计
- 接入权限
- 接入统一异常与任务状态

### 12.3 Novel

novel 域必须：

- 统一 ingestion / analysis / task / storage 边界
- 接入主干鉴权
- 接入 RBAC
- 接入审计与任务系统

### 12.4 本阶段标准

扩展域第一阶段不是追求“功能最全”，而是追求：

- 可接入
- 可鉴权
- 可授权
- 可审计
- 可追踪
- 可稳定运行

---

## 13. 关键后端资源设计

### 13.1 Auth / Admin

提供：

- 登录
- refresh
- logout
- current user
- sessions
- users CRUD
- roles CRUD
- permissions 查询
- role assignment
- API key management
- audit logs

### 13.2 Sources

提供：

- book_sources CRUD
- rss_sources CRUD
- subscriptions CRUD
- filter_rules CRUD
- source search/test hooks
- source export

### 13.3 Engine

提供：

- generate
- evaluate
- repair
- test harness
- job / result 查询

### 13.4 Dashboard / Health / Export

必须提供真正可用的聚合与诊断数据，不再允许：

- `page_size=1` 后做 `len(items)` 计数
- groups 永远空数组
- 参数命名漂移

### 13.5 System

提供：

- system settings
- audit query
- job status
- service status

---

## 14. 配置与本机运行策略

### 14.1 Python 与依赖

明确支持：

- Python 3.13

并修正依赖定义，使后端无需手工补丁安装即可启动。

### 14.2 数据库

- 默认采用项目内本地 SQLite 文件
- 不再默认 `/data/legado_hub.db`
- 启动时自动准备必要目录

### 14.3 Redis

- 可用时提供缓存/限流/队列
- 不可用时必须可降级
- 降级行为要显式、可观察

### 14.4 根路由

后端不再假设容器内固定前端路径。

可选策略后续实现时定为其一：

- 明确返回 API 服务信息
- 或仅在存在静态产物时提供静态前端

但无论如何不得再硬编码 `/app/frontend/index.html`。

---

## 15. 实施顺序

1. 新主干基础设施  
   config / security / auth / token / RBAC / audit / response / error / schema

2. 新主 API 核心资源  
   auth / users / roles / permissions / api-keys / sessions / audit / system

3. 源管理主链路  
   book_sources / rss_sources / subscriptions / filter_rules / export / dashboard / health

4. 规则引擎主链路  
   parse / execute / validate / evaluate / repair / generate / test harness

5. 扩展域接入并修稳  
   ai / translation / novel

6. 本机运行与验证收尾  
   Python 3.13 / SQLite / pytest / 前后端联通

---

## 16. 测试策略

### 16.1 单元测试

- security
- token/session
- RBAC
- response/error
- rule parser / selector / evaluator / repairer

### 16.2 应用服务测试

- auth service
- source service
- engine service
- translation service
- AI service
- novel service

### 16.3 API 集成测试

- 登录 / refresh / logout
- 权限放行 / 拒绝
- users / roles / permissions
- API key lifecycle
- sources CRUD
- export / dashboard / health
- engine generate / repair / evaluate / test
- AI / translation / novel 核心接口

### 16.4 本机验证

- Python 3.13
- SQLite
- `pytest`
- 前端与新 API 联通

---

## 17. 风险与约束

### 17.1 范围风险

本子项目仍然很大，因此实现时必须分阶段提交，不允许一把梭式混改。

### 17.2 规则引擎风险

规则链路影响 sources、engine、search/test 与扩展域，必须先统一结果模型，再替换调用面。

### 17.3 鉴权接入风险

一旦切到统一 auth/RBAC，接口大面积失效的风险很高，因此必须先做 auth contract，再逐资源挂载。

### 17.4 扩展域稳定性风险

AI / translation / novel 当前代码组织较散，第一阶段需要先把运行边界统一，再逐条修稳主路径。

---

## 18. 完成标准

本阶段完成时应满足：

- 运行时只有一套新主 API
- 旧 v0 / v1 / 并行 router 树不再作为运行主线
- 后端在本机 Python 3.13 可稳定启动
- SQLite schema 为新主干 schema
- Access + Refresh Token 可用
- 完整 RBAC 可用
- Sources / Engine / Dashboard / Export / Health 可用
- AI / translation / novel 接入新主干并达到稳定可控
- 后续后台管理面板可直接对接新主 API 继续演进

