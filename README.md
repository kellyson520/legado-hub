# LegadoHub Pro - Legado 云化阅读平台

LegadoHub Pro 是基于 Legado（阅读）订阅源协议的企业级中转 Docker 服务。采用 **DDD（领域驱动设计）四层架构**，在原有聚合、筛选、检测、写源能力基础上，全面升级了 **API Key 鉴权体系**、**AI 增强服务**、**LLM 翻译引擎**、**书源搜索**、**Redis 缓存层**、**源兼容性兜底机制** 和 **生产级部署架构**。

---

## 核心特性

### v2.1 新增能力

| 模块 | 特性 | 说明 |
|------|------|------|
| **书源搜索** | BookSearcher | 适配 Legado searchUrl 格式，支持 JSONPath/CSS 双模式解析，GET/POST/charset |
| **LLM 翻译** | 分块翻译引擎 | 从 md3 移植，ContentChunker 分块 + LLM/Google 双翻译器 + 词典记忆 |

### v2.0 Pro 能力

| 模块 | 特性 | 说明 |
|------|------|------|
| **鉴权体系** | API Key + JWT 双认证 | `lh_` 前缀密钥，SHA256 哈希存储，支持 12 项细粒度权限 |
| **配额管控** | 日调用上限 / 并发限制 | fetch 次数、AI 字符数、存储上限实时追踪 |
| **Redis 缓存** | 限流 / 配额计数 / 任务队列 | 滑动窗口限流，原子配额计数，源检测结果缓存 |
| **AI 增强** | 6 大 AI 服务 | 人物关系、世界观、剧情时间线、智能问答、书源修复、内容审查 |
| **兼容性引擎** | 5 大网站模板 + 通用兜底 | 起点、笔趣阁、69书吧、纵横、晋江，未知站点通用规则兜底 |
| **WebSocket** | 实时推送 | 源状态变更、任务进度、系统通知、配额告警 |
| **审计日志** | 全链路记录 | 90 天自动归档，支持按 action / key 过滤 |
| **生产部署** | Docker Compose 全栈 | Redis + MinIO + Nginx + 主服务，健康检查 + 自动重启 |

### 原有能力

| 功能 | 说明 |
|------|------|
| 订阅源聚合 | 定时拉取多个订阅链接，自动合并书源与订阅源 |
| 高级正则屏蔽 | 支持正则/文本过滤规则，可按名称、URL、分组、内容屏蔽 |
| 自动写源引擎 | 输入网站 URL 自动分析页面结构，生成 Legado 书源/订阅源规则 |
| Web 前端管理 | 提供完整的管理界面，支持增删改查、批量导入导出 |
| 定时可用性检查 | 自动检测源可用性，Redis 缓存结果，自动禁用长期失效源 |
| 统一输出 | 输出纯净的 Legado 兼容 JSON，支持 API 直链订阅 |

---

## DDD 分层架构

```
请求流: CORS -> TraceMiddleware -> RateLimitMiddleware -> AuditLogMiddleware -> 路由

┌──────────────────────────────────────────────────────────────────┐
│                     Interfaces 接口层                            │
│  v0 兼容 API: sources / health / engine / output                 │
│  v1 Pro API:  auth / ai / websocket / translate                  │
│  依赖注入: dependencies.py (get_source_service / get_auth ...)   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                   Application 应用层                              │
│  SourceAppService / AuthAppService / TranslationAppService        │
│  编排领域对象，调用仓储，发布事件                                 │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                     Domain 领域层                                │
│  实体: BookSource / RssSource / Subscription / FilterRule       │
│        User / UserGroup / ApiKey / AuditLog / QuotaUsage         │
│        TranslationJob / TranslationChunk / TextChunk             │
│        TranslationDictionary / TranslationStatus / TranslationProvider │
│        AICharacterResult / AIWorldResult / AIStorylineResult     │
│  仓储接口: SourceRepository / UserRepository / TranslationRepo    │
│  纯业务逻辑，不依赖任何基础设施                                   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                Infrastructure 基础设施层                            │
│  持久化: SQLite (factory 模式，可热切换 backend)                 │
│  缓存: MemoryCacheProvider (抽象接口 + 内存实现)                 │
│  外部服务: BookSearcher / LLMTranslator / GoogleTranslator      │
│  连接池: CrawlerPool (aiohttp 连接复用)                          │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                       Core 核心层                                │
│  config / security / dependencies / events / exceptions          │
│  logging / middleware / redis_client / response / compatibility   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 部署架构

```
┌─────────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Nginx (80)    │────▶│  LegadoHub  │────▶│  Redis (缓存)   │
│  反向代理+静态   │     │   (8000)    │     │  限流/配额/队列  │
└─────────────────┘     └─────────────┘     └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │  MinIO (9000)   │
                       │  对象存储/备份   │
                       └─────────────────┘
```

---

## 快速开始

### 1. 克隆并配置

```bash
git clone <仓库地址>
cd legado-hub
cp .env.example .env
# 编辑 .env，设置 SECRET_KEY 和 LLM_API_KEY
```

### 2. Docker Compose 启动

```bash
docker-compose up -d
```

服务启动后访问 `http://localhost`

### 3. 初始化管理员

首次访问时，点击登录页的「初始化管理员」，设置用户名和密码。

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SECRET_KEY` | *(必须修改)* | JWT 签名密钥，生产环境必须自定义 |
| `DB_PATH` | `/data/legado_hub.db` | SQLite 数据库路径 |
| `REPO_BACKEND` | `sqlite` | 仓储后端（sqlite / memory） |
| `REDIS_URL` | `redis://redis:6379/0` | Redis 连接地址 |
| `MINIO_ROOT_USER` | `legadohub` | MinIO 管理员账号 |
| `MINIO_ROOT_PASSWORD` | *(必须修改)* | MinIO 管理员密码 |
| `LLM_API_URL` | *(可选)* | 大模型 API 地址（OpenAI 兼容格式） |
| `LLM_API_KEY` | *(可选)* | 大模型 API 密钥 |
| `LLM_MODEL` | `gpt-4o` | 模型名称 |
| `DEBUG` | `false` | 调试模式（开启后暴露 /docs 和 /redoc） |
| `LOG_LEVEL` | `INFO` | 日志级别（DEBUG / INFO / WARNING / ERROR） |

---

## API 文档

### 认证方式

- **管理员**: `Authorization: Bearer <JWT Token>`
- **API Key**: `Authorization: Bearer lh_xxxxxxxx...`

### v0 兼容 API（无需认证）

#### 书源管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /api/sources/book` | GET | 书源列表（分页、分组、状态筛选） |
| `GET /api/sources/book/{url}` | GET | 获取单个书源 |
| `POST /api/sources/book` | POST | 创建书源 |
| `PUT /api/sources/book/{url}` | PUT | 更新书源 |
| `DELETE /api/sources/book/{url}` | DELETE | 删除书源 |
| `POST /api/sources/book/import` | POST | 批量导入书源 |
| `POST /api/sources/book/search` | POST | 书源搜索（关键词 + 源适配） |

#### 订阅源管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /api/sources/rss` | GET | 订阅源列表 |
| `GET /api/sources/rss/{url}` | GET | 获取单个订阅源 |
| `POST /api/sources/rss` | POST | 创建订阅源 |
| `DELETE /api/sources/rss/{url}` | DELETE | 删除订阅源 |
| `POST /api/sources/rss/import` | POST | 批量导入订阅源 |

#### 订阅与过滤规则

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /api/sources/subscriptions` | GET | 订阅列表 |
| `POST /api/sources/subscriptions` | POST | 创建订阅 |
| `DELETE /api/sources/subscriptions/{sub_id}` | DELETE | 删除订阅 |
| `GET /api/sources/filters` | GET | 过滤规则列表 |
| `POST /api/sources/filters` | POST | 创建过滤规则 |
| `DELETE /api/sources/filters/{rule_id}` | DELETE | 删除过滤规则 |

#### 健康检查

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /api/health/check` | GET | 批量检查源可用性 |
| `GET /api/health/check/{source_type}/{url}` | GET | 检查单个源 |

#### 写源引擎

| 接口 | 方法 | 说明 |
|------|------|------|
| `POST /api/engine/generate` | POST | 智能写源（含兼容性兜底） |
| `POST /api/engine/repair` | POST | 修复已有书源 |
| `POST /api/engine/evaluate` | POST | 兼容性评分 |

#### 统一输出

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /api/output/book` | GET | 输出书源（Legado 格式） |
| `GET /api/output/rss` | GET | 输出订阅源（Legado 格式） |
| `GET /api/output/all` | GET | 统一输出 |
| `GET /api/output/export.json` | GET | 导出 JSON 文件 |

#### 系统状态

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /api/status` | GET | 服务状态（版本、架构、存储后端） |

### v1 Pro API（需认证）

#### 认证管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `POST /api/v1/auth/setup` | POST | 初始化管理员 |
| `POST /api/v1/auth/login` | POST | 管理员登录 |
| `GET /api/v1/auth/keys` | GET | API Key 列表 |
| `POST /api/v1/auth/keys` | POST | 创建 API Key |
| `DELETE /api/v1/auth/keys/{key_id}` | DELETE | 删除 API Key |
| `GET /api/v1/auth/quota` | GET | 配额查询 |
| `GET /api/v1/auth/verify` | GET | 权限验证 |
| `GET /api/v1/auth/users` | GET | 用户列表 |
| `GET /api/v1/auth/audit` | GET | 审计日志 |

#### AI 增强服务

| 接口 | 方法 | 说明 |
|------|------|------|
| `POST /api/v1/llm/character` | POST | 人物关系提取 |
| `POST /api/v1/llm/world` | POST | 世界观解析 |
| `POST /api/v1/llm/storyline` | POST | 剧情时间线 |
| `POST /api/v1/llm/chat` | POST | 智能问答 |
| `POST /api/v1/llm/fix` | POST | 书源修复建议 |
| `POST /api/v1/llm/review` | POST | 内容合规审查 |
| `GET /api/v1/llm/character/{book_url}` | GET | 获取人物关系缓存结果 |
| `GET /api/v1/llm/world/{book_url}` | GET | 获取世界观缓存结果 |
| `GET /api/v1/llm/storyline/{book_url}` | GET | 获取剧情时间线缓存结果 |

#### LLM 翻译服务（从 md3 移植）

| 接口 | 方法 | 说明 |
|------|------|------|
| `POST /api/v1/translate/chapter` | POST | 翻译章节（支持 LLM / Google 双提供商） |
| `GET /api/v1/translate/jobs` | GET | 翻译任务列表 |
| `GET /api/v1/translate/jobs/{job_id}` | GET | 翻译任务详情 |
| `GET /api/v1/translate/jobs/{job_id}/result` | GET | 翻译结果（支持部分结果实时查看） |
| `DELETE /api/v1/translate/jobs/{job_id}` | DELETE | 删除翻译任务 |
| `GET /api/v1/translate/dictionary/{book_url}` | GET | 获取书籍翻译词典 |
| `POST /api/v1/translate/dictionary/{book_url}` | POST | 更新书籍翻译词典 |
| `GET /api/v1/translate/chunker/preview` | GET | 预览文本分块结果 |

#### WebSocket 实时推送

| 接口 | 方法 | 说明 |
|------|------|------|
| `WS /api/ws/events` | WebSocket | 实时事件通道 |
| 订阅 | `{"action": "subscribe", "channels": ["source", "task", "system"]}` | |
| 心跳 | `{"action": "ping"}` | |

---

## 权限体系

API Key 支持 12 项细粒度权限控制：

| 权限 | 说明 |
|------|------|
| `source_read` | 读取书源/订阅源 |
| `source_import` | 导入书源 |
| `source_edit` | 编辑/删除书源 |
| `source_publish` | 发布/导出书源 |
| `ai_character` | 人物关系 AI 分析 |
| `ai_world` | 世界观 AI 分析 |
| `ai_storyline` | 剧情时间线 AI 分析 |
| `ai_chat` | 智能问答 |
| `ai_fix` | AI 书源修复 |
| `view_sensitive` | 查看敏感内容 |
| `export` | 导出数据 |

---

## 定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| 订阅拉取 | 每 2 小时 | 自动拉取所有启用的订阅链接 |
| 可用性检查 | 每 4 小时 | 检查源可用性，Redis 缓存结果 |
| 失效源标记 | 每天 03:00 | 自动禁用 7 天未恢复的错误源 |
| 配额重置 | 每天 00:00 | 重置所有 API Key 的日配额 |
| 配额同步 | 每 30 分钟 | Redis 配额计数同步到数据库 |
| 日志归档 | 每周日 02:00 | 删除超过 90 天的审计日志 |

---

## 项目结构

```
legado-hub/
├── backend/
│   ├── app/
│   │   ├── main.py                         # FastAPI 入口（DDD 架构）
│   │   ├── database.py                     # [遗留] 旧版 ORM 模型，仅供 routers/ 使用
│   │   ├── models.py                       # [遗留] 旧版 Pydantic 模型，仅供 routers/ 使用
│   │   │
│   │   ├── core/                           # 核心层（横切关注点）
│   │   │   ├── config.py                   # 配置中心
│   │   │   ├── security.py                 # 密钥哈希 / JWT 签发验证
│   │   │   ├── dependencies.py             # 认证上下文 / 权限检查 / get_current_user
│   │   │   ├── redis_client.py             # Redis 封装（缓存/限流/配额计数）
│   │   │   ├── events.py                   # 事件总线（MemoryEventBus + 领域事件）
│   │   │   ├── exceptions.py               # 统一异常体系（BaseAppException + 9 子类）
│   │   │   ├── response.py                 # 统一响应格式（ok / fail / paginated）
│   │   │   ├── logging.py                  # JSON 结构化日志 + trace_id 上下文传播
│   │   │   ├── middleware.py               # Trace / RateLimit / AuditLog 中间件
│   │   │   └── compatibility.py            # 源兼容性引擎（5 站点模板 + 通用兜底）
│   │   │
│   │   ├── domain/                         # 领域层（纯业务对象）
│   │   │   ├── entities/
│   │   │   │   ├── source.py               # BookSource / RssSource / Subscription / FilterRule
│   │   │   │   ├── user.py                 # User / UserGroup / ApiKey / AuditLog / QuotaUsage
│   │   │   │   ├── translation.py          # TranslationJob / TranslationChunk / TextChunk
│   │   │   │   │                            # TranslationDictionary / TranslationStatus / TranslationProvider
│   │   │   │   └── ai_result.py            # AICharacterResult / AIWorldResult / AIStorylineResult
│   │   │   └── repositories/
│   │   │       ├── source_repo.py          # 源仓储接口（抽象）
│   │   │       ├── user_repo.py            # 用户仓储接口（抽象）
│   │   │       └── translation_repo.py     # 翻译仓储接口（抽象）
│   │   │
│   │   ├── application/                    # 应用层（业务编排）
│   │   │   └── services/
│   │   │       ├── source_service.py       # 书源 CRUD + 导出 + 事件发布
│   │   │       ├── auth_service.py         # 认证 / 用户 / API Key / 审计
│   │   │       └── translation_service.py  # 翻译任务管理 / 词典 / 结果查询
│   │   │
│   │   ├── infrastructure/                 # 基础设施层
│   │   │   ├── cache/
│   │   │   │   ├── abstract.py            # 缓存抽象接口
│   │   │   │   └── memory_cache.py        # 内存缓存实现
│   │   │   └── persistence/
│   │   │       ├── factory.py            # 仓储工厂（热切换 backend）
│   │   │       └── sqlite/
│   │   │           ├── source_repo_impl.py
│   │   │           ├── user_repo_impl.py
│   │   │           └── translation_repo_impl.py
│   │   │
│   │   ├── interfaces/                     # 接口层（HTTP 端点）
│   │   │   └── api/
│   │   │       ├── dependencies.py        # FastAPI 依赖注入（get_source_service 等）
│   │   │       ├── v0/                    # 兼容 API（无需认证）
│   │   │       │   ├── sources.py         # 书源/订阅源/订阅/过滤规则 CRUD + 搜索
│   │   │       │   ├── health.py          # 可用性检查
│   │   │       │   ├── engine.py          # 写源引擎（生成/修复/评分）
│   │   │       │   └── output.py          # 统一输出（Legado 格式）
│   │   │       └── v1/                    # Pro API（需认证）
│   │   │           ├── auth.py            # 认证管理
│   │   │           ├── ai.py              # AI 增强服务
│   │   │           ├── websocket.py       # WebSocket 实时推送
│   │   │           └── translate.py      # LLM 翻译服务
│   │   │
│   │   ├── services/                       # 核心服务
│   │   │   ├── fetcher.py                # 订阅拉取 / 可用性检查 / CrawlerPool
│   │   │   ├── generator.py              # 自动写源引擎（HTML 分析 + 兼容兜底）
│   │   │   ├── book_searcher.py          # 书源搜索（JSONPath + CSS 选择器）
│   │   │   └── translator.py             # 翻译引擎（ContentChunker + LLM/Google）
│   │   │
│   │   ├── routers/                        # [遗留] 旧版直连数据库路由（未被 main.py 注册）
│   │   │   ├── sources.py                 #   旧版书源管理（路径用单数 /subscription /filter）
│   │   │   ├── auth.py                   #   旧版认证（含额外 /groups、/users 端点）
│   │   │   ├── ai.py                     #   旧版 AI（权限名用 use_ 前缀）
│   │   │   ├── health.py                 #   旧版健康检查
│   │   │   ├── engine.py                 #   旧版写源引擎
│   │   │   ├── output.py                 #   旧版统一输出（含 _clean_hub_fields）
│   │   │   └── websocket.py              #   旧版 WebSocket
│   │   │
│   │   ├── api/routers/                    # [遗留] 旧版路由副本（未被 main.py 注册）
│   │   │   ├── sources.py                 #   旧版源管理
│   │   │   ├── health.py                 #   旧版健康检查
│   │   │   ├── engine.py                 #   旧版写源引擎
│   │   │   └── output.py                 #   旧版统一输出
│   │   │
│   │   ├── modules/
│   │   │   └── event_handlers.py         # 事件处理器注册
│   │   │
│   │   └── tasks/
│   │       └── scheduler.py              # APScheduler 定时任务（6 个任务）
│   │
│   ├── tests/                             # 测试（529+ 用例）
│   ├── scripts/
│   │   └── search_douluo.py              # 书源搜索脚本
│   ├── requirements.txt
│   ├── pytest.ini
│   └── Dockerfile
├── frontend/
│   └── index.html                         # SPA 管理界面
├── nginx/
│   └── nginx.conf                         # Nginx 反向代理配置
├── docker-compose.yml                     # 生产级部署配置
├── .env.example                          # 环境变量模板
└── README.md
```

---

## 技术栈

- **后端**: Python 3.11, FastAPI, SQLAlchemy 2.0, APScheduler, python-jose, passlib, redis-py
- **异步 HTTP**: aiohttp（搜索/翻译/订阅拉取连接池）, httpx（测试客户端）
- **HTML 解析**: beautifulsoup4, lxml（书源搜索 + 写源引擎）
- **RSS 解析**: feedparser（订阅源解析）
- **缓存/队列**: Redis 7
- **对象存储**: MinIO
- **前端**: 原生 HTML/CSS/JS 单页应用
- **代理**: Nginx（反向代理 + Gzip + 静态文件）
- **容器**: Docker, Docker Compose

---

## 兼容性引擎

当自动写源引擎无法完美解析目标网站时，系统会自动启用兼容性规则兜底：

**已知网站模板**：
- 起点中文网 (`qidian.com`)
- 笔趣阁系列 (`biquge*.cc/com/net/org`)
- 69书吧 (`69shu.top/com`)
- 纵横中文网 (`zongheng.com`)
- 晋江文学城 (`jx.la`)

**未知网站**：自动应用通用 CSS 选择器兜底规则，生成可运行的基础书源。

---

## 书源搜索

`BookSearcher` 适配 Legado 书源规则，支持两种解析模式：

- **JSONPath 模式**：当 `ruleSearch.bookList` 以 `$` 开头时，递归查找 JSON 字段，支持 `&&` 多值回退
- **CSS 选择器模式**：解析 HTML 响应，支持 `class.`/`id.`/`tag.` 前缀、`@attr` 属性提取、`||` 选择器回退、`##` 正则清洗

searchUrl 格式：`URL{,"method":"POST","body":"key={{key}}","charset":"gbk"}`

---

## 翻译引擎

从 [HapeLee/legado-with-MD3](https://github.com/HapeLee/legado-with-MD3) PR #1094 移植的 LLM 翻译功能：

- **ContentChunker**：按段落/句子边界分块，超长段落自动拆分，支持自定义块大小
- **LLMTranslator**：调用 OpenAI 兼容 API，解析 `[dictionary] + [result]` 输出格式，支持术语词典累积和指数退避重试
- **GoogleTranslator**：免费 Google 翻译 API，无需密钥
- **PartialTranslationAssembler**：已翻译块与原文混合组装，支持实时进度查看

---

## 协议

本项目遵循 Legado 开源书源/订阅源 JSON 格式规范，与 [gedoor/legado](https://github.com/gedoor/legado) 完全兼容。

## 相关项目

- [gedoor/legado](https://github.com/gedoor/legado) - 阅读 App 官方仓库
- [gedoor/legado_web_source_editor](https://github.com/gedoor/legado_web_source_editor) - 官方 Web 书源编辑器
- [HapeLee/legado-with-MD3](https://github.com/HapeLee/legado-with-MD3) - MD3 风格分支（翻译功能来源）
