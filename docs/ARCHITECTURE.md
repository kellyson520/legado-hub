# LegadoHub Pro 架构说明

版本: 2.1.0

本文档从宏观到微观说明 LegadoHub Pro 的架构设计、分层职责、数据流向和模块解耦机制。

---

## 目录

1. [整体架构](#整体架构)
2. [核心层（Core）](#核心层core)
3. [领域层（Domain）](#领域层domain)
4. [应用层（Application）](#应用层application)
5. [基础设施层（Infrastructure）](#基础设施层infrastructure)
6. [接口层（Interface）](#接口层interface)
7. [事件驱动架构](#事件驱动架构)
8. [部署架构](#部署架构)

---

## 整体架构

### DDD 四层架构

LegadoHub Pro 采用领域驱动设计（DDD）四层架构，从上到下依次为：

```
+--------------------------+
|       接口层 (Interface)   |  <-- FastAPI 路由、WebSocket、请求/响应转换
|  app/interfaces/api/v0    |
|  app/interfaces/api/v1    |
+--------------------------+
|       应用层 (Application) |  <-- 用例编排、事务边界、事件发布
|  app/application/services |
+--------------------------+
|       领域层 (Domain)      |  <-- 实体、值对象、仓储接口、业务规则
|  app/domain/entities      |
|  app/domain/repositories  |
+--------------------------+
|     基础设施层 (Infrastructure)|  <-- 数据库、缓存、外部服务、降级策略
|  app/infrastructure/persistence |
|  app/infrastructure/cache   |
+--------------------------+
|       核心层 (Core)        |  <-- 跨层共享基础设施（日志、异常、事件总线）
|  app/core/                |
+--------------------------+
```

**依赖规则**：上层可以调用下层，下层不能反向依赖上层。核心层被所有层共享。

### 数据流向

```
HTTP Request
    |
    v
[TraceMiddleware] -> 生成 Trace ID，注入日志上下文
    |
    v
[RateLimitMiddleware] -> Redis 滑动窗口限流检查
    |
    v
[AuditLogMiddleware] -> 写操作异步记录审计日志
    |
    v
[Interface 路由] -> 参数解析、调用 Application Service
    |
    v
[Application Service] -> 编排 Domain 对象、发布事件
    |
    v
[Domain Entity/Repository] -> 执行业务规则、持久化
    |
    v
[Infrastructure] -> SQLite / Redis / MemoryCache
    |
    v
[Event Bus] -> 异步分发领域事件到订阅者
    |
    v
[Event Handlers] -> 审计、统计、告警、WebSocket 推送
```

### 模块依赖关系

```
main.py
|-- core (被所有模块依赖)
|   |-- logging
|   |-- exceptions
|   |-- response
|   |-- events
|   |-- dependencies
|   |-- middleware
|   |-- redis_client
|   |-- compatibility
|   |-- security
|   |-- config
|
|-- domain (无外部依赖，纯 Python)
|   |-- entities
|   |-- repositories (抽象接口)
|
|-- application (依赖 domain 和 core)
|   |-- source_service
|   |-- auth_service
|
|-- infrastructure (依赖 domain 和 core)
|   |-- persistence/factory
|   |-- persistence/sqlite
|   |-- cache/memory_cache
|
|-- interfaces (依赖 application 和 core)
|   |-- api/v0
|   |-- api/v1
|   |-- api/dependencies
|
|-- modules (依赖 core)
|   |-- event_handlers
|
|-- services (辅助服务)
|   |-- fetcher
|   |-- generator
|
|-- tasks
|   |-- scheduler
```

---

## 核心层（Core）

核心层提供跨所有层共享的基础设施能力，是系统的"脊柱"。

### logging.py — JSON 结构化日志、上下文传播

职责：
- 全局日志配置初始化（`setup_logging`）
- JSON 结构化日志输出（便于 ELK/Loki 收集）
- 线程本地上下文传播（trace_id, user_id, api_key_id）
- 文件轮转 + 控制台双输出
- 错误日志单独文件（`error.log`）

关键类/函数：

| 名称 | 类型 | 说明 |
|------|------|------|
| `JSONFormatter` | class | 将日志记录格式化为 JSON |
| `ContextAdapter` | class | 带上下文的日志适配器 |
| `setup_logging` | function | 初始化日志系统 |
| `get_logger(name)` | function | 获取统一 logger |
| `set_log_context` | function | 设置当前线程日志上下文 |
| `get_trace_id` | function | 获取当前 trace_id |

示例：

```python
from app.core.logging import get_logger, set_log_context

logger = get_logger("source_manager")
set_log_context(trace_id="abc123", user_id="42")
logger.info("拉取订阅完成", extra={"action": "fetch", "source_url": "..."})
```

输出示例：

```json
{"timestamp": "2024-01-15T08:30:00Z", "level": "INFO", "logger": "source_manager",
 "message": "拉取订阅完成", "module": "source_manager", "trace_id": "abc123",
 "user_id": "42", "action": "fetch", "source_url": "..."}
```

### exceptions.py — 统一异常体系、全局处理器

职责：
- 定义所有业务异常基类（`BaseAppException`）
- 每个异常自动映射 HTTP 状态码和业务错误码
- 全局异常处理器注册到 FastAPI
- 兜底未捕获异常

异常层次：

```
BaseAppException (status_code=500, error_code="INTERNAL_ERROR")
|-- ValidationException (400, "VALIDATION_ERROR")
|-- AuthenticationException (401, "AUTHENTICATION_ERROR")
|-- AuthorizationException (403, "AUTHORIZATION_ERROR")
|-- NotFoundException (404, "NOT_FOUND")
|-- ConflictException (409, "CONFLICT")
|-- RateLimitException (429, "RATE_LIMIT_EXCEEDED")
|-- QuotaExceededException (429, "QUOTA_EXCEEDED")
|-- ExternalServiceException (502, "EXTERNAL_SERVICE_ERROR")
|-- StorageException (500, "STORAGE_ERROR")
```

全局处理器注册：

```python
from app.core.exceptions import register_exception_handlers

register_exception_handlers(app)  # app: FastAPI 实例
```

### response.py — 统一响应格式

职责：
- 定义标准响应模型（`UnifiedResponse`）
- 提供便捷构造函数：`ok`, `created`, `paginated`, `fail`, `from_exception`
- 自动注入 `trace_id`

函数签名：

```python
def ok(data=None, message="success", meta=None) -> dict
def created(data=None, message="创建成功") -> dict
def paginated(items, total, page, page_size, message="success") -> dict
def fail(message="操作失败", code="ERROR", data=None, details=None) -> dict
def from_exception(exc) -> dict
```

### events.py — 事件总线、12 种领域事件

职责：
- 定义领域事件基类（`DomainEvent`）和 12 种具体事件
- 提供事件总线抽象接口（`EventBus`）
- 提供内存事件总线实现（`MemoryEventBus`）
- 支持异步队列分发，失败不影响发布者

预定义领域事件：

| 事件类 | 触发场景 |
|--------|---------|
| `SourceFetchedEvent` | 订阅源拉取完成 |
| `SourceStatusChangedEvent` | 源可用性状态变更 |
| `SourceCreatedEvent` | 新源创建 |
| `SourceUpdatedEvent` | 源字段更新 |
| `SourceDeletedEvent` | 源删除 |
| `FilterRuleTriggeredEvent` | 过滤规则匹配 |
| `QuotaUsageEvent` | 配额使用记录 |
| `QuotaExceededEvent` | 配额超限告警 |
| `AIAnalysisCompletedEvent` | AI 分析完成 |
| `AuditEvent` | 审计动作 |
| `SystemNoticeEvent` | 系统通知 |

使用方式：

```python
from app.core.events import publish_event, SourceCreatedEvent

await publish_event(SourceCreatedEvent(
    source_url="https://example.com",
    source_name="示例书源",
    source_type="book"
))
```

### dependencies.py — 认证上下文、权限守卫

职责：
- 提取并校验 `Authorization: Bearer` 头
- 支持 API Key（`lh_` 前缀）和 JWT Token 两种认证方式
- 构建 `AuthContext`（携带权限、用户、Key 信息）
- 配额检查与 Redis 计数
- 权限守卫装饰器：`require_admin`, `require_permission`

关键类：

```python
class AuthContext:
    api_key_id: Optional[int]
    api_key_name: Optional[str]
    user_id: Optional[int]
    username: Optional[str]
    is_admin: bool
    permissions: dict
    
    def has_permission(self, permission: str) -> bool
```

关键依赖函数：

| 函数 | 说明 |
|------|------|
| `get_auth_context` | FastAPI Depends，提取并验证凭证 |
| `require_admin` | FastAPI Depends，要求管理员权限 |
| `require_permission(permission)` | 返回 Depends，要求指定权限 |

### middleware.py — Trace/限流/审计中间件

三个中间件（按执行顺序从外到内）：

#### TraceMiddleware
- 从请求头提取 `X-Trace-ID`，不存在则生成
- 注入日志上下文
- 请求结束后清理上下文
- 记录请求耗时和状态码

#### RateLimitMiddleware
- Redis 滑动窗口限流
- 支持按 API Key 前缀或 IP 限流
- 触发限流时返回 429 + `Retry-After`
- Redis 不可用时降级为无限制

#### AuditLogMiddleware
- 仅记录写操作（POST/PUT/DELETE/PATCH）
- 异步记录审计日志到数据库
- 失败不阻断请求

### redis_client.py — Redis 封装、降级策略

职责：
- 单例模式管理 Redis 连接
- 自动重连和连接健康检查
- 所有操作异常时降级（返回默认值，不抛异常）
- 提供缓存、限流、配额、队列四种能力

关键方法：

| 方法 | 说明 |
|------|------|
| `get` / `set` / `delete` | 字符串缓存 |
| `get_json` / `set_json` | JSON 缓存 |
| `check_rate_limit` | 滑动窗口限流 |
| `increment_quota` / `get_quota` | 配额计数 |
| `enqueue_task` / `dequeue_task` | 任务队列 |
| `cache_source_check` | 源可用性缓存 |

降级行为：Redis 不可用时，限流返回通过，缓存返回 None，配额返回 0。

### compatibility.py — 兼容性规则引擎

职责：
- 维护常见书源网站的兼容性规则模板（起点中文网、笔趣阁、纵横、晋江等）
- 提供通用兜底规则（`FALLBACK_RULES`）
- 从 URL 自动生成书源（`generate_from_url`）
- 修复已有书源常见问题（`repair_source`）
- 评估书源兼容性得分（`get_compatibility_score`）

核心类：

```python
class CompatibilityEngine:
    @staticmethod
    def match_site(url: str) -> Optional[str]
    @staticmethod
    def get_site_rules(site_key: str) -> dict
    @staticmethod
    def apply_fallback(source: dict) -> dict
    @staticmethod
    def generate_from_url(url: str, source_name=None) -> dict
    @staticmethod
    def repair_source(source: dict) -> dict
    @staticmethod
    def get_compatibility_score(source: dict) -> dict
```

---

## 领域层（Domain）

领域层是系统的核心，包含纯 Python 实现的业务对象，不依赖任何框架或基础设施。

### 实体类

#### BookSource — 书源实体

```python
@dataclass
class BookSource:
    bookSourceUrl: str          # 唯一标识
    bookSourceName: str
    bookSourceGroup: Optional[str]
    enabled: bool = True
    sourceStatus: str = "unknown"
    ruleSearch: Optional[dict] = None
    ruleToc: Optional[dict] = None
    ruleContent: Optional[dict] = None
    # ... 其他 Legado 标准字段
    
    @property
    def id(self) -> str:
        return self.bookSourceUrl
    
    def is_available(self) -> bool:
        return self.enabled and self.sourceStatus == "ok"
    
    def mark_checked(self, status: str, error_msg=None):
        self.sourceStatus = status
        self.lastCheckTime = datetime.utcnow()
        self.errorMsg = error_msg
    
    def to_legado_dict(self) -> dict:
        # 移除内部字段，输出 Legado 兼容格式
```

#### RssSource — 订阅源实体

结构与 `BookSource` 类似，以 `sourceUrl` 为唯一标识。

#### Subscription — 订阅实体

```python
@dataclass
class Subscription:
    id: int = 0
    name: str = ""
    url: str = ""
    subType: str = "book"      # book, rss, mixed
    enabled: bool = True
    autoFetch: bool = True
    fetchInterval: int = 3600
    
    def mark_fetched(self, source_count: int = 0):
        self.lastFetchTime = datetime.utcnow()
        self.sourceCount = source_count
```

#### FilterRule — 过滤规则实体

```python
@dataclass
class FilterRule:
    id: int = 0
    name: str = ""
    pattern: str = ""
    isRegex: bool = True
    scope: Optional[str] = None   # sourceName, sourceUrl, sourceGroup, content
    
    def should_filter(self, source_name="", source_url="", source_group="", content="") -> bool:
        # 业务规则：判断是否匹配过滤条件
```

#### User / ApiKey / AuditLog / QuotaUsage — 用户相关实体

```python
@dataclass
class User:
    id: int = 0
    username: str = ""
    role: str = "user"          # admin, user, viewer
    is_active: bool = True

@dataclass
class ApiKey:
    id: int = 0
    key_hash: str = ""
    name: Optional[str] = None
    is_enabled: bool = True
    expires_at: Optional[datetime] = None
    permissions: Optional[dict] = None
    daily_fetch_quota: int = 500
    daily_ai_quota: int = 100000
```

### 仓储接口（Repository）

领域层只定义仓储抽象接口，不依赖具体存储实现。

#### SourceRepository

```python
class SourceRepository(ABC):
    # BookSource
    @abstractmethod
    async def get_book_source(self, url: str) -> Optional[BookSource]: ...
    
    @abstractmethod
    async def list_book_sources(self, group, status, enabled_only, page, page_size) -> tuple[list, int]: ...
    
    @abstractmethod
    async def save_book_source(self, source: BookSource) -> BookSource: ...
    
    @abstractmethod
    async def delete_book_source(self, url: str) -> bool: ...
    
    # RssSource
    @abstractmethod
    async def get_rss_source(self, url: str) -> Optional[RssSource]: ...
    
    # Subscription
    @abstractmethod
    async def list_subscriptions(self, enabled_only=False) -> list[Subscription]: ...
    
    # FilterRule
    @abstractmethod
    async def list_filter_rules(self, enabled_only=True) -> list[FilterRule]: ...
```

#### UserRepository

类似地定义用户、API Key、审计日志、配额使用的 CRUD 接口。

### 业务规则

业务规则封装在实体方法中，例如：

- `BookSource.is_available()` — 源是否可用（enabled + status == ok）
- `FilterRule.should_filter()` — 规则是否匹配给定内容
- `BookSource.to_legado_dict()` — 移除内部字段，输出标准格式

---

## 应用层（Application）

应用层负责用例编排，是领域层的"导演"。不直接操作数据库，而是通过仓储接口。

### SourceAppService — 源管理用例编排

```python
class SourceAppService:
    def __init__(self, source_repo: SourceRepository):
        self._repo = source_repo
    
    async def create_book_source(self, data: dict, created_by=None) -> BookSource:
        source = BookSource.from_dict(data)
        result = await self._repo.save_book_source(source)
        
        # 发布领域事件（模块间解耦）
        await event_bus.publish(SourceCreatedEvent(
            source_url=source.bookSourceUrl,
            source_name=source.bookSourceName,
            source_type="book",
            created_by=created_by
        ))
        return result
    
    async def update_book_source(self, url: str, data: dict) -> BookSource:
        existing = await self._repo.get_book_source(url)
        # 字段对比，记录变更
        changed_fields = [...]
        result = await self._repo.save_book_source(existing)
        
        await event_bus.publish(SourceUpdatedEvent(
            source_url=url,
            changed_fields=changed_fields
        ))
        return result
    
    async def delete_book_source(self, url: str) -> bool:
        source = await self._repo.get_book_source(url)
        result = await self._repo.delete_book_source(url)
        
        await event_bus.publish(SourceDeletedEvent(
            source_url=url,
            source_name=source.bookSourceName,
            source_type="book"
        ))
        return result
```

### AuthAppService — 认证用例编排

```python
class AuthAppService:
    def __init__(self, user_repo: UserRepository):
        self._repo = user_repo
    
    async def login(self, username: str, password: str) -> str:
        user = await self._repo.get_user_by_username(username)
        if not verify_password(password, user.password_hash):
            raise AuthenticationException("用户名或密码错误")
        return create_access_token({"sub": str(user.id), ...})
    
    async def create_api_key(self, name: str, permissions=None) -> tuple[str, ApiKey]:
        raw_key = generate_api_key()        # lh_xxx
        key_hash = hash_api_key(raw_key)
        key = ApiKey(key_hash=key_hash, name=name, permissions=permissions)
        saved = await self._repo.save_api_key(key)
        return raw_key, saved
```

### 事件发布

应用服务在创建/更新/删除操作时自动发布领域事件，实现模块间完全解耦：

| 操作 | 发布事件 |
|------|---------|
| 创建书源 | `SourceCreatedEvent` |
| 更新书源 | `SourceUpdatedEvent` |
| 删除书源 | `SourceDeletedEvent` |
| 创建 RSS 源 | `SourceCreatedEvent` |
| 删除 RSS 源 | `SourceDeletedEvent` |

---

## 基础设施层（Infrastructure）

基础设施层提供领域层定义的具体实现，支持热切换存储后端。

### RepositoryFactory — 仓储工厂

```python
class RepositoryFactory:
    _source_repo: Optional[SourceRepository] = None
    _user_repo: Optional[UserRepository] = None
    
    @classmethod
    def get_source_repo(cls) -> SourceRepository:
        if cls._source_repo is None:
            backend = os.environ.get("REPO_BACKEND", "sqlite").lower()
            if backend == "sqlite":
                cls._source_repo = SQLiteSourceRepository()
            elif backend == "memory":
                cls._source_repo = MemorySourceRepository()
        return cls._source_repo
```

通过环境变量 `REPO_BACKEND` 热切换：
- `sqlite` — SQLite 持久化（默认，小 VPS 零依赖）
- `memory` — 内存存储（仅用于测试）

### SQLite 实现 — ORM 到 Entity 转换

`SQLiteSourceRepository` 和 `SQLiteUserRepository` 实现仓储接口：

```python
class SQLiteSourceRepository(SourceRepository):
    def _to_entity_book(self, model: BookSourceModel) -> BookSource:
        data = {k: v for k, v in model.__dict__.items() if not k.startswith("_")}
        return BookSource.from_dict(data)
    
    async def get_book_source(self, url: str) -> Optional[BookSource]:
        db = SessionLocal()
        try:
            model = db.query(BookSourceModel).filter(...).first()
            return self._to_entity_book(model) if model else None
        finally:
            db.close()
```

转换规则：
- 读取时：ORM Model -> dict -> Entity（通过 `from_dict`）
- 写入时：Entity -> dict -> ORM Model（通过 `setattr` 或构造函数）

### MemoryCacheProvider — LRU+TTL 降级缓存

```python
class MemoryCacheProvider(CacheProvider):
    def __init__(self, max_size: int = 10000):
        self._data = {}
        self._expires = {}
        self._lock = threading.RLock()
    
    async def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._data or self._is_expired(key):
                return None
            return self._data[key]
    
    async def set(self, key: str, value: Any, expire: int = 3600) -> bool:
        with self._lock:
            if len(self._data) >= self._max_size:
                self._cleanup_expired()
                if len(self._data) >= self._max_size:
                    oldest = next(iter(self._data))  # LRU 淘汰
                    self._data.pop(oldest)
            self._data[key] = value
            self._expires[key] = time.time() + expire
```

特点：
- 纯 Python 字典，零外部依赖
- 线程安全（`threading.RLock`）
- 惰性过期清理
- 内存上限保护 + LRU 淘汰

---

## 接口层（Interface）

接口层是系统的"门面"，负责接收 HTTP/WebSocket 请求并转换为应用层调用。

### v0 兼容路由

路径前缀：`/api/sources`, `/api/health`, `/api/engine`, `/api/output`

设计原则：
- 保持与旧版 LegadoHub 的 URL 和响应格式兼容
- 不直接操作数据库，只调用 `SourceAppService`
- 返回统一响应格式（`ok()`, `paginated()`, `fail()`）

```python
router = APIRouter(prefix="/api/sources", tags=["sources"])

@router.get("/book")
async def list_book_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    svc: SourceAppService = Depends(get_source_service)
):
    items, total = await svc.list_book_sources(...)
    return paginated([item.__dict__ for item in items], total, page, page_size)
```

### v1 Pro 路由

路径前缀：`/api/v1/auth`, `/api/v1/llm`, `/api/ws`

设计原则：
- 新功能（AI、认证、WebSocket）
- 需要 Bearer Token 认证
- 管理员接口使用 `require_admin` 依赖

```python
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.get("/keys")
async def list_api_keys(
    auth: AuthContext = Depends(require_admin)
):
    ...
```

### FastAPI Depends 注入

接口层通过 `app/interfaces/api/dependencies.py` 注入应用服务：

```python
def get_source_service() -> SourceAppService:
    repo = get_source_repo()          # 从工厂获取仓储
    return SourceAppService(repo)

def get_auth_service() -> AuthAppService:
    repo = get_user_repo()
    return AuthAppService(repo)
```

---

## 事件驱动架构

### MemoryEventBus — 异步队列分发

```python
class MemoryEventBus(EventBus):
    def __init__(self):
        self._handlers = {}           # event_name -> [handler_fn]
        self._queue = asyncio.Queue() # 事件队列
        self._worker_task = None
    
    def subscribe(self, event_type: Type[DomainEvent]) -> Callable:
        # 装饰器注册处理器
        
    async def publish(self, event: DomainEvent) -> None:
        await self._queue.put(event)
    
    async def _worker(self) -> None:
        while self._running:
            event = await self._queue.get()
            await self._dispatch(event)
            self._queue.task_done()
```

特点：
- 同进程内异步分发
- 事件队列缓冲，削峰填谷
- 一个处理器失败不影响其他处理器
- 启动/停止与应用生命周期绑定

### 事件处理器（审计、统计、告警）

在 `app/modules/event_handlers.py` 中注册：

```python
@on_event(SourceCreatedEvent)
async def audit_source_created(event: SourceCreatedEvent):
    logger.info(f"[Audit] 源创建: {event.source_name}")

@on_event(SourceFetchedEvent)
async def stats_source_fetched(event: SourceFetchedEvent):
    logger.info(f"[Stats] 订阅拉取完成: {event.subscription_name}")

@on_event(QuotaExceededEvent)
async def alert_quota_exceeded(event: QuotaExceededEvent):
    logger.warning(f"[Alert] 配额超限: key={event.api_key_id}")
```

### 模块完全解耦

模块间通信只能通过事件总线，禁止直接调用：

```
Application Service --发布事件--> EventBus --分发--> Handler A (审计)
                                          --分发--> Handler B (统计)
                                          --分发--> Handler C (WebSocket 推送)
                                          --分发--> Handler D (告警)
```

---

## 部署架构

### Docker Compose 部署

```yaml
services:
  redis:          # 缓存 + 限流 + 队列
  minio:          # 对象存储（可选，备份和 AI 结果）
  legado-hub:     # 主服务（FastAPI + SQLite）
  nginx:          # 反向代理 + 静态文件
```

### 小 VPS 友好设计

LegadoHub Pro 专为小 VPS（1核1G 或更低）设计，具有以下降级能力：

| 组件 | 完整模式 | 降级模式 |
|------|---------|---------|
| 数据库 | SQLite（零配置） | 内存模式（测试用） |
| 缓存 | Redis | MemoryCacheProvider（纯 Python） |
| 限流 | Redis 滑动窗口 | 无限制（Redis 断开时） |
| AI | OpenAI 兼容 API | Mock 模式（返回模板数据） |
| 对象存储 | MinIO | 不使用 |

资源占用：
- 仅运行 LegadoHub（无 Redis）：内存约 50-100MB
- 完整 Docker Compose：内存约 200-300MB
- SQLite 数据库：随数据量增长，通常 < 100MB

### 生产环境 checklist

1. 修改 `SECRET_KEY`（必须）
2. 配置 `LLM_API_URL` 和 `LLM_API_KEY`（如需 AI 功能）
3. 配置 `REDIS_URL`（如需分布式限流）
4. 定期备份 `/data/legado_hub.db`
5. Nginx 配置 HTTPS
