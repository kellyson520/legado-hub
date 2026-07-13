# LegadoHub Pro 代码说明

版本: 2.1.0

本文档面向开发者，说明项目目录结构、编码规范、关键设计模式和新增功能指南。

---

## 目录

1. [目录结构](#目录结构)
2. [编码规范](#编码规范)
3. [关键模式](#关键模式)
4. [新增功能指南](#新增功能指南)
5. [配置说明](#配置说明)
6. [测试指南](#测试指南)

---

## 目录结构

```
legado-hub/
|-- backend/
|   |-- app/
|   |   |-- __init__.py
|   |   |-- main.py                     # FastAPI 入口，生命周期管理，路由注册
|   |   |-- models.py                   # Pydantic 请求/响应模型（接口校验用）
|   |   |-- database.py                 # SQLAlchemy 引擎、Session、ORM 模型定义
|   |   |
|   |   |-- core/                       # 核心层：跨层共享基础设施
|   |   |   |-- __init__.py
|   |   |   |-- config.py               # 全局配置（Settings，Pydantic）
|   |   |   |-- logging.py              # JSON 结构化日志、上下文传播
|   |   |   |-- exceptions.py           # 统一异常体系、全局处理器
|   |   |   |-- response.py             # 统一响应格式（ok/fail/paginated）
|   |   |   |-- events.py               # 事件总线、12 种领域事件定义
|   |   |   |-- dependencies.py         # 认证上下文、权限守卫、配额检查
|   |   |   |-- middleware.py           # Trace/限流/审计中间件
|   |   |   |-- redis_client.py         # Redis 封装、降级策略
|   |   |   |-- compatibility.py        # 书源兼容性规则引擎
|   |   |   |-- security.py             # 密码哈希、JWT、API Key 生成
|   |   |
|   |   |-- domain/                     # 领域层：纯 Python 业务对象
|   |   |   |-- __init__.py
|   |   |   |-- entities/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- source.py           # BookSource, RssSource, Subscription, FilterRule
|   |   |   |   |-- user.py             # User, ApiKey, AuditLog, QuotaUsage
|   |   |   |   |-- ai_result.py        # AI 分析结果实体
|   |   |   |-- repositories/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- source_repo.py      # SourceRepository 抽象接口
|   |   |   |   |-- user_repo.py        # UserRepository 抽象接口
|   |   |
|   |   |-- application/                # 应用层：用例编排
|   |   |   |-- __init__.py
|   |   |   |-- services/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- source_service.py   # SourceAppService：源管理用例
|   |   |   |   |-- auth_service.py     # AuthAppService：认证用例
|   |   |
|   |   |-- infrastructure/             # 基础设施层：具体实现
|   |   |   |-- __init__.py
|   |   |   |-- persistence/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- factory.py          # RepositoryFactory：仓储工厂
|   |   |   |   |-- sqlite/
|   |   |   |   |   |-- __init__.py
|   |   |   |   |   |-- source_repo_impl.py  # SQLiteSourceRepository
|   |   |   |   |   |-- user_repo_impl.py    # SQLiteUserRepository
|   |   |   |-- cache/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- abstract.py         # CacheProvider 抽象接口
|   |   |   |   |-- memory_cache.py     # MemoryCacheProvider（LRU+TTL）
|   |   |
|   |   |-- interfaces/                 # 接口层：HTTP/WebSocket 路由
|   |   |   |-- __init__.py
|   |   |   |-- api/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- dependencies.py     # 接口层依赖注入（get_source_service 等）
|   |   |   |   |-- v0/                 # v0 兼容 API
|   |   |   |   |   |-- __init__.py
|   |   |   |   |   |-- sources.py      # /api/sources/*
|   |   |   |   |   |-- health.py       # /api/health/*
|   |   |   |   |   |-- engine.py       # /api/engine/*
|   |   |   |   |   |-- output.py       # /api/output/*
|   |   |   |   |-- v1/                 # v1 Pro API
|   |   |   |   |   |-- __init__.py
|   |   |   |   |   |-- auth.py         # /api/v1/auth/*
|   |   |   |   |   |-- ai.py           # /api/v1/llm/*
|   |   |   |   |   |-- websocket.py    # /api/ws/*
|   |   |
|   |   |-- modules/                    # 事件处理器模块
|   |   |   |-- __init__.py
|   |   |   |-- event_handlers.py       # 审计、统计、告警处理器注册
|   |   |
|   |   |-- services/                   # 辅助服务（非 DDD 核心）
|   |   |   |-- __init__.py
|   |   |   |-- fetcher.py              # 源可用性检查
|   |   |   |-- generator.py            # 自动写源引擎
|   |   |
|   |   |-- tasks/                      # 后台任务
|   |   |   |-- __init__.py
|   |   |   |-- scheduler.py            # 定时任务调度器
|   |   |
|   |   |-- routers/                    # 旧版路由（兼容保留）
|   |   |   |-- ...
|   |   |
|   |   |-- api/                        # 旧版 API 路由（兼容保留）
|   |   |   |-- routers/
|   |   |   |   |-- ...
|   |
|   |-- tests/                          # 测试目录
|   |   |-- __init__.py
|   |   |-- conftest.py                 # pytest 全局配置和 fixture
|   |   |-- test_api_*.py               # API 接口测试
|   |   |-- test_app_services.py        # 应用服务测试
|   |   |-- test_core_*.py              # 核心模块测试
|   |   |-- test_domain_*.py            # 领域实体测试
|   |   |-- test_infra_*.py             # 基础设施测试
|   |   |-- test_middleware.py          # 中间件测试
|   |   |-- test_scheduler.py           # 定时任务测试
|   |   |-- test_services_*.py          # 辅助服务测试
|   |
|   |-- pytest.ini                      # pytest 配置
|   |-- requirements.txt                # Python 依赖
|   |-- Dockerfile                      # 后端镜像构建
|
|-- frontend/
|   |-- index.html                      # 前端入口（静态页面）
|
|-- nginx/
|   |-- nginx.conf                      # Nginx 反向代理配置
|
|-- docker-compose.yml                  # Docker Compose 编排
|-- .env.example                        # 环境变量示例
|-- .dockerignore
|-- README.md
```

### 各目录职责说明

| 目录 | 职责 | 依赖方向 |
|------|------|---------|
| `app/core` | 跨层基础设施，被所有层依赖 | 无外部依赖 |
| `app/domain` | 业务实体和仓储接口，纯 Python | 仅依赖标准库 |
| `app/application` | 用例编排、事务、事件发布 | 依赖 domain 和 core |
| `app/infrastructure` | 数据库、缓存、外部服务实现 | 依赖 domain 和 core |
| `app/interfaces` | HTTP/WebSocket 路由、参数校验 | 依赖 application 和 core |
| `app/modules` | 事件处理器（跨模块通信） | 依赖 core |
| `app/services` | 辅助服务（爬虫、AI 引擎） | 依赖 core |
| `app/tasks` | 定时任务和后台任务 | 依赖 core 和 application |

---

## 编码规范

### 使用 async/await

所有 I/O 操作（数据库、HTTP、Redis）必须使用 `async/await`：

```python
# 正确
async def get_book_source(self, url: str) -> Optional[BookSource]:
    db = SessionLocal()
    try:
        model = db.query(BookSourceModel).filter(...).first()
        return self._to_entity_book(model) if model else None
    finally:
        db.close()

# 错误（阻塞事件循环）
def get_book_source(self, url: str):
    db = SessionLocal()
    model = db.query(...).first()  # 阻塞！
```

### 统一日志（get_logger）

禁止直接使用 `logging.getLogger()`，必须通过 `get_logger` 获取：

```python
from app.core.logging import get_logger

logger = get_logger("module_name")

# 基础日志
logger.info("操作完成")

# 结构化日志（推荐）
logger.info(
    "拉取订阅完成",
    extra={"action": "fetch", "source_url": "...", "count": 10}
)
```

日志会自动携带 `trace_id`、`user_id`、`api_key_id` 等上下文。

### 统一异常（禁止 HTTPException）

禁止在业务代码中抛出 FastAPI 的 `HTTPException`，必须使用自定义异常：

```python
# 正确
from app.core.exceptions import NotFoundException, ValidationException

raise NotFoundException(f"书源不存在: {url}")
raise ValidationException("请求参数错误", details={"field": "name"})

# 错误
from fastapi import HTTPException
raise HTTPException(status_code=404, detail="Not found")
```

自定义异常会自动被全局处理器捕获并转换为统一响应格式。

### 统一响应（ok/fail/paginated）

接口层返回响应必须使用 `response.py` 中的便捷函数：

```python
from app.core.response import ok, fail, paginated

# 成功（单条数据）
return ok(data, "书源创建成功")

# 成功（列表分页）
return paginated(items, total, page, page_size)

# 业务失败（非异常场景）
return fail("书源不可用", code="SOURCE_UNAVAILABLE")
```

### DDD 分层约束

**硬性规定**：

1. **Interface 层不直接操作 DB**
   - 只能调用 Application Service
   - 禁止 `from app.database import SessionLocal`

2. **Application 层不依赖基础设施**
   - 只能通过仓储接口操作数据
   - 禁止直接导入 SQLAlchemy 模型

3. **Domain 层零外部依赖**
   - 只能使用 Python 标准库
   - 禁止导入 FastAPI、SQLAlchemy、Redis 等

4. **Infrastructure 层实现 Domain 接口**
   - 必须继承 `SourceRepository`、`UserRepository` 等抽象类
   - 负责 ORM 模型与领域实体的双向转换

```python
# Interface 层（正确）
@app.get("/api/sources/book")
async def list_sources(svc: SourceAppService = Depends(get_source_service)):
    return await svc.list_book_sources(...)

# Interface 层（错误！直接操作 DB）
@app.get("/api/sources/book")
async def list_sources():
    db = SessionLocal()  # 禁止！
    return db.query(BookSourceModel).all()
```

---

## 关键模式

### 仓储模式（Repository Pattern）

**目的**：解耦领域层与数据存储，支持热切换存储后端。

**结构**：

```python
# domain/repositories/source_repo.py
class SourceRepository(ABC):
    @abstractmethod
    async def get_book_source(self, url: str) -> Optional[BookSource]: ...

# infrastructure/persistence/sqlite/source_repo_impl.py
class SQLiteSourceRepository(SourceRepository):
    async def get_book_source(self, url: str) -> Optional[BookSource]:
        # SQLite 实现

# infrastructure/persistence/factory.py
class RepositoryFactory:
    @classmethod
    def get_source_repo(cls) -> SourceRepository:
        if backend == "sqlite":
            return SQLiteSourceRepository()
```

**使用**：

```python
# application/services/source_service.py
class SourceAppService:
    def __init__(self, source_repo: SourceRepository):
        self._repo = source_repo
```

### 工厂模式（RepositoryFactory）

**目的**：根据配置动态创建仓储实例，避免硬编码。

```python
# 通过环境变量切换后端
os.environ["REPO_BACKEND"] = "sqlite"   # 或 "memory"

repo = RepositoryFactory.get_source_repo()
```

**测试时重置**：

```python
RepositoryFactory.reset()  # 清除单例缓存
```

### 事件驱动（Event-Driven）

**目的**：模块间完全解耦，不直接调用对方代码。

**发布事件**：

```python
from app.core.events import publish_event, SourceCreatedEvent

await publish_event(SourceCreatedEvent(
    source_url="https://example.com",
    source_name="示例书源",
    source_type="book"
))
```

**订阅事件**：

```python
from app.core.events import on_event, SourceCreatedEvent

@on_event(SourceCreatedEvent)
async def handle_source_created(event: SourceCreatedEvent):
    print(f"新源创建: {event.source_name}")
```

**启动注册**：

```python
# app/modules/event_handlers.py
def register_all_handlers():
    # 装饰器已自动注册，此函数确保模块被加载
    pass

# app/main.py
from app.modules import register_all_handlers
register_all_handlers()
```

### 依赖注入（FastAPI Depends）

**目的**：解耦接口层与应用层，便于测试和替换实现。

```python
# interfaces/api/dependencies.py
def get_source_service() -> SourceAppService:
    repo = get_source_repo()
    return SourceAppService(repo)

# interfaces/api/v0/sources.py
@router.get("/book")
async def list_book_sources(
    svc: SourceAppService = Depends(get_source_service)
):
    return await svc.list_book_sources(...)
```

**认证依赖**：

```python
from app.core.dependencies import get_auth_context, require_admin

# 需要认证
@router.post("/generate")
async def generate(auth: AuthContext = Depends(get_auth_context)):
    ...

# 需要管理员
@router.get("/keys")
async def list_keys(auth: AuthContext = Depends(require_admin)):
    ...
```

---

## 新增功能指南

### 1. 新增实体

以新增 `Bookmark`（书签）实体为例：

**步骤 1**：在 `app/domain/entities/` 下创建实体

```python
# app/domain/entities/bookmark.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Bookmark:
    id: int = 0
    user_id: int = 0
    book_url: str = ""
    chapter_url: str = ""
    chapter_name: str = ""
    position: int = 0          # 阅读位置（字符数）
    createdAt: datetime = field(default_factory=datetime.utcnow)
    updatedAt: datetime = field(default_factory=datetime.utcnow)
```

**步骤 2**：在 `app/database.py` 添加 ORM 模型

```python
class BookmarkModel(Base):
    __tablename__ = "bookmarks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    book_url = Column(String, nullable=False)
    chapter_url = Column(String, nullable=True)
    chapter_name = Column(String, nullable=True)
    position = Column(Integer, default=0)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 2. 新增仓储方法

**步骤 1**：在仓储接口中声明方法

```python
# app/domain/repositories/source_repo.py（或新建 bookmark_repo.py）
class BookmarkRepository(ABC):
    @abstractmethod
    async def get_bookmark(self, bookmark_id: int) -> Optional[Bookmark]: ...
    
    @abstractmethod
    async def list_bookmarks(self, user_id: int) -> list[Bookmark]: ...
    
    @abstractmethod
    async def save_bookmark(self, bookmark: Bookmark) -> Bookmark: ...
    
    @abstractmethod
    async def delete_bookmark(self, bookmark_id: int) -> bool: ...
```

**步骤 2**：在 SQLite 实现中实现方法

```python
# app/infrastructure/persistence/sqlite/bookmark_repo_impl.py
class SQLiteBookmarkRepository(BookmarkRepository):
    async def get_bookmark(self, bookmark_id: int) -> Optional[Bookmark]:
        db = SessionLocal()
        try:
            model = db.query(BookmarkModel).filter(BookmarkModel.id == bookmark_id).first()
            return self._to_entity(model) if model else None
        finally:
            db.close()
    
    def _to_entity(self, model: BookmarkModel) -> Bookmark:
        return Bookmark(
            id=model.id,
            user_id=model.user_id,
            book_url=model.book_url,
            chapter_url=model.chapter_url,
            chapter_name=model.chapter_name,
            position=model.position,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
        )
```

**步骤 3**：在工厂中注册

```python
# app/infrastructure/persistence/factory.py
from .sqlite.bookmark_repo_impl import SQLiteBookmarkRepository

class RepositoryFactory:
    _bookmark_repo: Optional[BookmarkRepository] = None
    
    @classmethod
    def get_bookmark_repo(cls) -> BookmarkRepository:
        if cls._bookmark_repo is None:
            backend = os.environ.get("REPO_BACKEND", "sqlite").lower()
            if backend == "sqlite":
                cls._bookmark_repo = SQLiteBookmarkRepository()
            else:
                raise ValueError(f"不支持的存储后端: {backend}")
        return cls._bookmark_repo
```

### 3. 新增应用服务

```python
# app/application/services/bookmark_service.py
from typing import List, Optional
from ...domain.repositories.bookmark_repo import BookmarkRepository
from ...domain.entities.bookmark import Bookmark
from ...core.exceptions import NotFoundException

class BookmarkAppService:
    def __init__(self, bookmark_repo: BookmarkRepository):
        self._repo = bookmark_repo
    
    async def create_bookmark(self, user_id: int, book_url: str, 
                              chapter_url: str, chapter_name: str, 
                              position: int = 0) -> Bookmark:
        bookmark = Bookmark(
            user_id=user_id,
            book_url=book_url,
            chapter_url=chapter_url,
            chapter_name=chapter_name,
            position=position
        )
        return await self._repo.save_bookmark(bookmark)
    
    async def get_bookmark(self, bookmark_id: int) -> Bookmark:
        bookmark = await self._repo.get_bookmark(bookmark_id)
        if not bookmark:
            raise NotFoundException(f"书签不存在: {bookmark_id}")
        return bookmark
    
    async def list_user_bookmarks(self, user_id: int) -> List[Bookmark]:
        return await self._repo.list_bookmarks(user_id)
```

### 4. 新增 API 端点

```python
# app/interfaces/api/v1/bookmark.py
from fastapi import APIRouter, Depends
from typing import List

from ....core.response import ok, paginated
from ....core.dependencies import get_auth_context, AuthContext
from ....core.exceptions import ValidationException
from ....application.services.bookmark_service import BookmarkAppService
from ..dependencies import get_bookmark_service

router = APIRouter(prefix="/api/v1/bookmarks", tags=["bookmarks"])

@router.get("")
async def list_bookmarks(
    auth: AuthContext = Depends(get_auth_context),
    svc: BookmarkAppService = Depends(get_bookmark_service)
):
    """列出当前用户的书签"""
    items = await svc.list_user_bookmarks(auth.user_id or 0)
    return ok([item.__dict__ for item in items])

@router.post("")
async def create_bookmark(
    data: dict,
    auth: AuthContext = Depends(get_auth_context),
    svc: BookmarkAppService = Depends(get_bookmark_service)
):
    """创建书签"""
    if not data.get("book_url"):
        raise ValidationException("book_url 不能为空")
    
    result = await svc.create_bookmark(
        user_id=auth.user_id or 0,
        book_url=data["book_url"],
        chapter_url=data.get("chapter_url"),
        chapter_name=data.get("chapter_name"),
        position=data.get("position", 0)
    )
    return ok(result.__dict__, "书签创建成功")

@router.get("/{bookmark_id}")
async def get_bookmark(
    bookmark_id: int,
    auth: AuthContext = Depends(get_auth_context),
    svc: BookmarkAppService = Depends(get_bookmark_service)
):
    """获取单个书签"""
    bookmark = await svc.get_bookmark(bookmark_id)
    return ok(bookmark.__dict__)
```

注册路由：

```python
# app/main.py
from .interfaces.api.v1 import bookmark

app.include_router(bookmark.router)
```

### 5. 新增事件类型和处理器

**步骤 1**：在 `app/core/events.py` 定义事件

```python
@dataclass
class BookmarkCreatedEvent(DomainEvent):
    bookmark_id: int = 0
    user_id: int = 0
    book_url: str = ""
    chapter_name: str = ""
```

**步骤 2**：在应用服务中发布事件

```python
# app/application/services/bookmark_service.py
from ...core.events import publish_event, BookmarkCreatedEvent

class BookmarkAppService:
    async def create_bookmark(self, ...):
        result = await self._repo.save_bookmark(bookmark)
        await publish_event(BookmarkCreatedEvent(
            bookmark_id=result.id,
            user_id=result.user_id,
            book_url=result.book_url,
            chapter_name=result.chapter_name
        ))
        return result
```

**步骤 3**：在 `app/modules/event_handlers.py` 注册处理器

```python
from app.core.events import on_event, BookmarkCreatedEvent

@on_event(BookmarkCreatedEvent)
async def handle_bookmark_created(event: BookmarkCreatedEvent):
    logger.info(
        f"[Bookmark] 新书签: user={event.user_id}, book={event.book_url}",
        extra={"action": "bookmark_created", "user_id": event.user_id}
    )
```

---

## 配置说明

### .env 环境变量

复制 `.env.example` 为 `.env`，按需修改：

```bash
# 安全（生产环境必须修改！）
SECRET_KEY=your-super-secret-key-change-this-in-production

# 数据库
DB_PATH=/data/legado_hub.db

# Redis
REDIS_URL=redis://redis:6379/0

# MinIO（对象存储）
MINIO_ROOT_USER=legadohub
MINIO_ROOT_PASSWORD=legadohub-minio-password

# LLM（可选）
LLM_API_URL=https://api.openai.com/v1/chat/completions
LLM_API_KEY=sk-your-openai-api-key
LLM_MODEL=gpt-4o

# 开发调试
DEBUG=false
LOG_LEVEL=INFO
```

### config.py 配置项

```python
from app.core.config import settings

# 常用配置
settings.APP_NAME           # "LegadoHub Pro"
settings.APP_VERSION        # "2.1.0"
settings.DEBUG              # bool
settings.LOG_LEVEL          # "INFO"
settings.REPO_BACKEND       # "sqlite" | "memory"
settings.DB_PATH            # "/data/legado_hub.db"
settings.REDIS_URL          # "redis://localhost:6379/0"
settings.SECRET_KEY         # JWT 签名密钥
settings.RATE_LIMIT_PER_MINUTE  # 60
settings.DEFAULT_DAILY_FETCH_QUOTA  # 500
settings.DEFAULT_DAILY_AI_QUOTA     # 100000
settings.LLM_MODEL          # "gpt-4o"
```

### Docker Compose 配置

```yaml
services:
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru

  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-legadohub}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-legadohub-minio-password}
    command: server /data --console-address ":9001"

  legado-hub:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
      - ./frontend:/app/frontend:ro
      - ./logs:/app/logs
    environment:
      - DB_PATH=/data/legado_hub.db
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY:-legado-hub-change-me-in-production}
      - DEBUG=false
    depends_on:
      redis:
        condition: service_healthy

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./frontend:/app/frontend:ro
    depends_on:
      - legado-hub
```

**启动命令**：

```bash
docker-compose up -d
```

**查看日志**：

```bash
docker-compose logs -f legado-hub
```

---

## 测试指南

### pytest 运行方式

```bash
# 进入后端目录
cd backend

# 运行全部测试
pytest

# 运行指定测试文件
pytest tests/test_core_events.py

# 运行指定测试函数
pytest tests/test_core_events.py::test_publish_event

# 显示详细输出
pytest -v

# 生成覆盖率报告
pytest --cov=app --cov-report=html
```

### conftest.py fixture

```python
# tests/conftest.py
import pytest
import os

# 测试环境配置
os.environ.setdefault("REPO_BACKEND", "sqlite")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# asyncio 模式
pytestmark = pytest.mark.asyncio

# 全新事件总线
@pytest.fixture
def fresh_event_bus():
    from app.core.events import MemoryEventBus
    return MemoryEventBus()

# 已启动的事件总线
@pytest.fixture
async def started_event_bus(fresh_event_bus):
    await fresh_event_bus.start()
    yield fresh_event_bus
    await fresh_event_bus.stop()

# 内存缓存
@pytest.fixture
def cache_provider():
    from app.infrastructure.cache.memory_cache import MemoryCacheProvider
    return MemoryCacheProvider(max_size=100)

# 模拟请求
@pytest.fixture
def mock_request():
    from unittest.mock import MagicMock
    request = MagicMock()
    request.url.path = "/test/path"
    request.method = "GET"
    return request

# 示例数据
@pytest.fixture
def sample_book_source_data():
    return {
        "bookSourceUrl": "https://example.com",
        "bookSourceName": "测试书源",
        "enabled": True,
        "sourceStatus": "ok",
    }
```

### mock 策略

**Mock 仓储（隔离应用服务测试）**：

```python
# tests/test_app_services.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.application.services.source_service import SourceAppService
from app.domain.entities.source import BookSource

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get_book_source = AsyncMock()
    repo.save_book_source = AsyncMock()
    repo.list_book_sources = AsyncMock(return_value=([], 0))
    return repo

@pytest.fixture
def source_service(mock_repo):
    return SourceAppService(mock_repo)

async def test_create_book_source(source_service, mock_repo):
    mock_repo.save_book_source.return_value = BookSource(
        bookSourceUrl="https://example.com",
        bookSourceName="测试书源"
    )
    
    result = await source_service.create_book_source({
        "bookSourceUrl": "https://example.com",
        "bookSourceName": "测试书源"
    })
    
    assert result.bookSourceUrl == "https://example.com"
    mock_repo.save_book_source.assert_awaited_once()
```

**Mock 事件总线**：

```python
# tests/test_core_events.py
import pytest
from app.core.events import MemoryEventBus, SourceCreatedEvent

async def test_event_dispatch(started_event_bus):
    received = []
    
    @started_event_bus.subscribe(SourceCreatedEvent)
    async def handler(event):
        received.append(event.source_name)
    
    await started_event_bus.publish(SourceCreatedEvent(
        source_url="https://example.com",
        source_name="测试书源",
        source_type="book"
    ))
    
    # 等待异步处理
    await asyncio.sleep(0.1)
    
    assert "测试书源" in received
```

**Mock Redis（测试降级逻辑）**：

```python
# tests/test_middleware.py
import pytest
from unittest.mock import MagicMock, patch
from app.core.middleware import RateLimitMiddleware
from fastapi import FastAPI, Request

@pytest.fixture
def app():
    return FastAPI()

async def test_rate_limit_degraded(app):
    middleware = RateLimitMiddleware(app)
    
    # Mock Redis 未连接
    with patch("app.core.middleware.redis_client") as mock_redis:
        mock_redis.is_connected = False
        mock_redis.check_rate_limit = AsyncMock(return_value=(True, 60, 0))
        
        # 构造请求
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.client.host = "127.0.0.1"
        request.headers = {}
        
        # 应该通过（降级模式）
        response = await middleware.dispatch(request, lambda req: MagicMock())
        assert response is not None
```

**使用内存后端（集成测试）**：

```python
# tests/test_api_health.py
import pytest
import os

# 强制使用内存后端
os.environ["REPO_BACKEND"] = "memory"

from app.infrastructure.persistence.factory import RepositoryFactory

@pytest.fixture(autouse=True)
def reset_factory():
    RepositoryFactory.reset()
    yield
    RepositoryFactory.reset()

async def test_health_check():
    from app.services.fetcher import SourceChecker
    checker = SourceChecker()
    result = await checker.check_book_source({"bookSourceUrl": "https://example.com"})
    assert "status" in result
```

### 测试目录约定

| 测试文件 | 测试目标 |
|---------|---------|
| `test_api_*.py` | API 接口层（路由） |
| `test_app_services.py` | 应用服务（用例编排） |
| `test_core_*.py` | 核心模块（日志、异常、事件、响应等） |
| `test_domain_*.py` | 领域实体（业务规则） |
| `test_infra_*.py` | 基础设施（缓存、仓储实现） |
| `test_middleware.py` | 中间件（Trace、限流、审计） |
| `test_scheduler.py` | 定时任务 |
| `test_services_*.py` | 辅助服务（fetcher、generator） |
