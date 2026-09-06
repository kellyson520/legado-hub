# LegadoHub Pro

LegadoHub Pro 是面向 Legado（阅读）书源协议的可审计阅读与内容分析平台，提供书源导入、规则运行、健康探测、自动写源、Agent 工具调用、多源互补和人物/剧情/世界观分析。

当前运行架构、依赖方向和扩展规则以 [`docs/ARCHITECTURE_CURRENT.md`](docs/ARCHITECTURE_CURRENT.md) 为准；开发约定见 [`docs/CODE_GUIDE.md`](docs/CODE_GUIDE.md)。

## 能力

- Legado 规则解析、JS bridge、原生运行时和统一安全 HTTP 出站。
- 书源候选、审核、发布、健康探测、分页、临时租户测试和 JSON 导入导出。
- Agent 书源检查/修复工具，以及基于真实章节证据的人物、剧情、世界观和时间线分析。
- 多源章节互补、内容指纹、证据存储、知识提案和审核流水线。
- OpenAI-compatible 多渠道供应商、路由、重试、降级、模型发现和配额控制。
- React 控制台：统一 API 客户端、认证刷新、流式事件、分页和中英文界面。

## 架构

```text
interfaces/http -> application/services -> domain
       |                  |                |
       |                  +-> application/ports
       +---------- composition root -> infrastructure

core: 日志、异常、响应、分页、认证、安全、脱敏和策略
```

领域事件载荷位于 `backend/app/domain/events.py`，事件总线只负责投递；SQLite、HTTP、Legado、浏览器和供应商实现都在 `backend/app/infrastructure`。前端只通过 `frontend/src/api` 访问服务端。

旧 `app.services`、`app.database` 和 `app.core.compatibility` 仅作为兼容入口，不是新的运行扩展点。

## 启动

### Docker Compose（低内存部署）

默认部署只启动 FastAPI 与 Nginx，API 使用单 worker，数据和日志全部挂载到宿主机；为保持镜像精简，默认不携带 Java/Kotlin native runtime，`LEGADO_RUNTIME_HEALTHCHECK_ENABLED=false`；Redis 是可选 profile；MinIO 和 Cloudflare Tunnel 使用独立 Compose override，启用时必须显式提供密码/token。

```bash
cp .env.example .env
# 生产环境必须修改 SECRET_KEY
mkdir -p data logs backups
docker compose up -d --build
docker compose ps
```

控制台默认地址：`http://127.0.0.1:8080`（可用 `.env` 中的 `WEB_PORT` 更换）。首次使用在登录页初始化管理员。

开发时可挂载源码（源码只读挂载，数据仍保存在宿主机）：

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml.example up -d --build
```

可选 Redis/MinIO：

```bash
docker compose --profile redis -f docker-compose.yml -f docker-compose.minio.yml up -d --build
```

### 公网访问（Cloudflare Tunnel）

公网模式不开放数据库、Redis 或 MinIO 端口，而是由 `cloudflared` 主动连接 Cloudflare。先在 Cloudflare Dashboard 创建 Tunnel，并把 Public Hostname 指向 `http://web:80`，再把 token 只写入本机 `.env`：

```bash
# .env（不要提交）
CLOUDFLARE_TUNNEL_TOKEN=真实的 tunnel token
docker compose -f docker-compose.yml -f docker-compose.public.yml up -d
```

公网配置渲染检查：

```bash
docker compose -f docker-compose.yml -f docker-compose.public.yml config
```

如果没有 Cloudflare token，不要启用 `public` profile。生产默认仍只绑定 `127.0.0.1:8080`。

### 后续源码更新

生产镜像默认固定构建时源码；更新代码后执行：

```bash
git pull
docker compose build --pull api web
docker compose up -d api web
```

开发模式使用 `docker-compose.override.yml.example` 的 bind mount，可直接替换 `backend/app` 或 `frontend/src` 后重建对应服务。SQLite 数据位于 `./data`，日志位于 `./logs`，备份位于 `./backups`；首次启动的 permissions 服务会为这些目录设置非 root API 所需权限。

### 本地开发

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
APP_ENV=test SECRET_KEY=local-dev-secret-key-32-bytes-minimum \
  .venv/bin/uvicorn app.main:app --reload --port 8000

cd ../frontend
npm ci
npm run dev
```

## 配置

| 变量 | 说明 |
| --- | --- |
| `SECRET_KEY` | JWT/会话签名密钥，生产环境必须自定义 |
| `DB_PATH` | SQLite 文件路径 |
| `REDIS_URL` | 限流、配额和缓存地址；不可用时按配置降级 |
| `LLM_API_URL` | OpenAI-compatible API 地址（可选） |
| `LLM_API_KEY` | 模型供应商密钥（可选，不写入仓库） |
| `LLM_MODEL` | 默认模型名称 |
| `DEBUG` | 是否暴露 FastAPI 调试文档 |
| `LOG_LEVEL` / `LOG_JSON` | 统一日志级别和格式 |

系统设置页也可以持久化供应商账户、模型路由和 Agent 设置；凭据只用于服务端调用，API 响应会脱敏。

## API 入口

所有后台接口使用统一 envelope 和 `/api` 前缀。当前路由族包括：

| 路由族 | 用途 |
| --- | --- |
| `/api/auth` | 登录、刷新、登出、当前用户 |
| `/api/admin` | 用户、API Key、审计 |
| `/api/sources` | 书源候选/发布/导入/导出/规则 |
| `/api/source-build` | 写源构建任务 |
| `/api/source-health` | 探针、健康快照、恢复和隔离 |
| `/api/engine` | Legado 规则评估、修复和部署 |
| `/api/reading`、`/api/client` | 阅读客户端安全读取和内容分发 |
| `/api/ai` | AI 会话、工具调用和任务 |
| `/api/novel`、`/api/novel-analysis` | 小说摄取、证据优先分析和审核 |
| `/api/work-knowledge` | 人物、事件、世界观和知识提案 |
| `/api/translation` | 翻译任务和结果 |
| `/api/system` | 分组设置、供应商路由和模型发现 |
| `/api/events`、`/api/jobs`、`/api/agent-runs` | 运行事件、任务和 Agent 轨迹 |
| `/api/interactive-browser` | 浏览器人工验证和回放 |

认证使用 `Authorization: Bearer <JWT>`；面向阅读客户端的 API Key 使用 `Authorization: Bearer lh_<key>`。生产环境不要把密钥放进前端源码或日志。

### TXT 到深度分析报告

小说分析默认先走确定性代码路径，不需要 LLM：上传 TXT 后按章节解析，再调用 `GET /api/novel-analysis/works/{work_id}/code-report?chapter_limit=8`。报告包含人物候选、窗口共现、时间表达、事件触发词和每项的章节 offset 证据；相同工作内容重复请求会命中 SHA-256 缓存。

建议流程：

1. 使用 `/api/novel` 的上传预览/导入接口导入 TXT，确认章节标题和切分结果。
2. 调用 `code-report`，先检查 `characters`、`time_mentions`、`events`、`cooccurrences` 的 evidence；相对时间（如“三天后”）会标记为 `unresolved`，不会自动当作绝对日期。
3. 只有需要别名归并、关系语义或未锚定时间归一化时，才创建 `/api/novel-analysis/works/{work_id}/tasks` 深析任务，并传入筛选后的 evidence ID。
4. 任务继承 `max_tokens_per_task`、`max_tool_calls_per_task`、`max_chapters_per_task` 上限；系统不会把整本小说直接发送给 LLM。

无 LLM provider 时，第 2 步仍可完成并返回可复核的代码分析报告。

## 验证

```bash
cd backend
.venv/bin/pytest -q
python3 -m compileall -q app tests

cd ../frontend
npm run test -- --run
npm run build
```

提交前运行 `git diff --check`，并确认没有提交构建缓存、SQLite 数据库、日志或凭据文件。
