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

### Docker Compose

```bash
cp .env.example .env
# 设置 SECRET_KEY；需要模型时再设置 LLM_API_URL / LLM_API_KEY / LLM_MODEL
docker compose up -d
```

控制台默认地址：`http://localhost`。首次使用在登录页初始化管理员。

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
