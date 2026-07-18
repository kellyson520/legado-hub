# LegadoHub Pro API 手册

版本：当前 `main` 分支

API 的唯一实现位于 `backend/app/interfaces/http`，由 `app.main` 挂载到 `/api`。旧的 `/api/v0`、`/api/v1`、`/api/output` 和 WebSocket 文档不再适用。

## 通用约定

基础地址：`http://localhost:8000`

请求和响应使用 UTF-8 JSON。成功响应：

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

分页列表的 `data` 是数组，`meta` 至少包含 `page`、`page_size`、`total`、`total_pages`。失败响应保持相同 envelope，`success=false` 并提供稳定业务码。

## 认证

管理控制台使用 JWT：

```http
Authorization: Bearer <access-token>
```

阅读客户端使用 API Key：

```http
Authorization: Bearer lh_<api-key>
```

登录、刷新和当前用户：

```text
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/auth/me
```

写操作按权限检查；未授权、权限不足和过期凭据分别返回 `401`/`403`，不要通过重复请求绕过权限。

## 路由族

以下是当前挂载的路由族。具体请求字段以对应模块和 OpenAPI（仅在 `DEBUG=true` 时暴露）为准。

| 路由 | 作用 |
| --- | --- |
| `/api/admin` | 用户、角色、API Key、审计查询和管理 |
| `/api/sources` | 书源候选/发布版本、规则编辑、JSON 导入导出 |
| `/api/source-build` | 写源构建任务、运行状态和审核流水线 |
| `/api/source-health` | 单源/批量探针、健康快照、恢复和隔离 |
| `/api/engine` | 规则评估、修复、harness、部署和运行记录 |
| `/api/reading` | 书籍搜索、目录和正文读取 |
| `/api/client` | API Key 客户端能力和内容分发 |
| `/api/ai` | AI 对话、工具调用、任务和权限边界 |
| `/api/novel` | 小说摄取和 Agent 任务 |
| `/api/novel-analysis` | 证据优先的分析、审核和任务状态 |
| `/api/work-knowledge` | 人物、事件、世界观、时间线知识提案 |
| `/api/translation` | 翻译任务、分块结果和审核 |
| `/api/system` | 分组设置、供应商账户、路由和模型发现 |
| `/api/events` | 运行事件查询和 SSE 事件流 |
| `/api/jobs` | 后台任务列表和详情 |
| `/api/agent-runs` | Agent 运行、工具调用和证据轨迹 |
| `/api/interactive-browser` | 浏览器验证会话、relay 和人工确认 |
| `/api/dashboard`、`/api/health` | 控制台统计和服务健康 |
| `/api/export` | 受权限保护的数据导出 |
| `/api/status` | 公共服务状态和运行时状态 |

## 书源生命周期

导入或 Agent 创建的规则先进入 `candidate` 版本。审核流水线负责：

1. 规则结构校验和兼容性评估。
2. 受限页面/Legado 运行时联合测试。
3. Agent 修复或人工验证（必要时进入浏览器验证会话）。
4. 只有审核通过的版本才能发布到阅读目录。

联合测试写入租户范围的临时书源，默认 15 分钟过期；不会直接修改已发布源。

## Agent 和小说分析

内容型问题必须先调用获授权的 `source.search`、`toc.get`、`chapter.fetch` 工具取得正文证据。工具结果进入 Agent 轨迹并经过脱敏；没有正文证据时，服务拒绝基于模型记忆输出人物生平、剧情、世界观或时间线结论。

系统设置中的供应商路由支持多渠道和模型发现。模型密钥只保存在服务端仓储，响应和审计记录不会返回原始密钥。

## 错误码

常见业务码：

| HTTP | 业务码 | 含义 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 参数或规则不合法 |
| 401 | `AUTHENTICATION_ERROR` | 凭据缺失/无效 |
| 403 | `AUTHORIZATION_ERROR` | 权限不足 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `CONFLICT` | 版本、状态或幂等冲突 |
| 429 | `RATE_LIMIT_EXCEEDED` / `QUOTA_EXCEEDED` | 限流或配额耗尽 |
| 502 | `EXTERNAL_SERVICE_ERROR` | 外部源/模型失败 |
| 500 | `INTERNAL_ERROR` / `STORAGE_ERROR` | 服务或存储异常 |

错误详情会经过 `app.core.redaction` 脱敏。客户端应记录 `trace_id`，不要记录 Authorization、Cookie、供应商密钥或完整上游响应。

## 测试

```bash
cd backend
.venv/bin/pytest -q
```

HTTP contract 测试位于 `backend/tests/test_api_*.py`；架构和依赖边界测试位于 `backend/tests/test_dependency_direction.py`。
