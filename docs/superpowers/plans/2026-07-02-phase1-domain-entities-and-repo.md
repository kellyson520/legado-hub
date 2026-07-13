# Phase 1: 领域实体 + 仓储接口 + SQLite 实现

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 NovelUnderstanding 系统的所有领域实体、枚举、仓储接口及 SQLite 实现，建立可测试的数据访问层。

**Architecture:** 遵循 DDD 分层，实体纯业务对象不依赖基础设施，仓储接口在 domain 层定义，SQLite 实现在 infrastructure 层。JSON 字段用 SQLite TEXT 存储。

**Tech Stack:** Python 3.11, dataclasses, aiosqlite, pytest-asyncio

---

## 文件结构

```
app/
├── domain/
│   ├── entities/
│   │   └── novel.py              # 所有 novel 领域实体 + 枚举
│   └── repositories/
│       └── novel_repo.py         # NovelRepository 抽象接口
├── infrastructure/
│   └── persistence/
│       └── sqlite/
│           └── novel_repo_impl.py # SQLite 实现
└── database_migrations/
    └── novel_schema.sql          # CREATE TABLE 语句
tests/
├── test_domain_entities.py       # 实体单元测试
└── test_novel_repo.py            # 仓储集成测试
```

---

### Task 1: Novel 枚举类

**Files:**
- Create: `app/domain/entities/novel.py` (前半部分：枚举)
- Test: `tests/test_domain_entities.py`

- [ ] **Step 1: 写枚举测试**

```python
# tests/test_domain_entities.py
import pytest
from app.domain.entities.novel import (
    NovelStatus, EntityType, RelationType, EventType, StateField, IngestSource
)

class TestNovelEnums:
    def test_novel_status_values(self):
        assert NovelStatus.PENDING.value == "pending"
        assert NovelStatus.READY.value == "ready"
        assert NovelStatus.ERROR.value == "error"

    def test_entity_type_values(self):
        assert EntityType.CHARACTER.value == "character"
        assert EntityType.REALM.value == "realm"

    def test_relation_type_values(self):
        assert RelationType.ALLY.value == "ally"
        assert RelationType.CUSTOM.value == "custom"

    def test_event_type_values(self):
        assert EventType.BATTLE.value == "battle"
        assert EventType.BREAKTHROUGH.value == "breakthrough"

    def test_state_field_values(self):
        assert StateField.REALM.value == "realm"
        assert StateField.EMOTION.value == "emotion"

    def test_ingest_source_values(self):
        assert IngestSource.BOOK_SOURCE.value == "book_source"
        assert IngestSource.UPLOAD.value == "upload"

    def test_enum_comparison(self):
        assert NovelStatus.READY == NovelStatus("ready")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py -v
```

Expected: ImportError / ModuleNotFoundError

- [ ] **Step 3: 实现所有枚举类**

```python
# app/domain/entities/novel.py
from enum import Enum


class NovelStatus(str, Enum):
    PENDING = "pending"
    INGESTING = "ingesting"
    SUMMARIZING = "summarizing"
    EXTRACTING = "extracting"
    READY = "ready"
    ERROR = "error"


class EntityType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
    FACTION = "faction"
    REALM = "realm"
    CONCEPT = "concept"


class RelationType(str, Enum):
    ALLY = "ally"
    ENEMY = "enemy"
    MASTER = "master"
    SUBORDINATE = "subordinate"
    LOVER = "lover"
    FAMILY = "family"
    RIVAL = "rival"
    CUSTOM = "custom"


class EventType(str, Enum):
    BATTLE = "battle"
    BREAKTHROUGH = "breakthrough"
    BETRAYAL = "betrayal"
    REUNION = "reunion"
    DISCOVERY = "discovery"
    DEPARTURE = "departure"
    DEATH = "death"
    CUSTOM = "custom"


class StateField(str, Enum):
    REALM = "realm"
    ABILITY = "ability"
    STATUS = "status"
    RELATIONSHIP = "relationship"
    POSSESSION = "possession"
    POSITION = "position"
    EMOTION = "emotion"
    CUSTOM = "custom"


class IngestSource(str, Enum):
    BOOK_SOURCE = "book_source"
    UPLOAD = "upload"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py::TestNovelEnums -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
cd /workspace/legado-hub && git add -A && git commit -m "feat: add novel domain enums"
```

---

### Task 2: NovelBook + NovelSourceMirror 实体

**Files:**
- Modify: `app/domain/entities/novel.py` (添加 dataclass)
- Modify: `tests/test_domain_entities.py`

- [ ] **Step 1: 写 NovelBook 测试**

在 `tests/test_domain_entities.py` 中添加：

```python
from dataclasses import fields
from datetime import datetime
from app.domain.entities.novel import NovelBook, NovelSourceMirror

class TestNovelBook:
    def test_default_values(self):
        book = NovelBook()
        assert book.id == 0
        assert book.book_url == ""
        assert book.status == NovelStatus.PENDING
        assert book.source_type == IngestSource.BOOK_SOURCE
        assert book.ingest_progress == 0.0
        assert book.total_chapters == 0

    def test_custom_values(self):
        book = NovelBook(
            id=1,
            book_url="https://example.com/book/1",
            book_name="Test Book",
            author="Test Author",
            status=NovelStatus.READY,
            total_chapters=100,
        )
        assert book.id == 1
        assert book.book_name == "Test Book"
        assert book.status == NovelStatus.READY

    def test_has_created_at(self):
        book = NovelBook()
        assert isinstance(book.created_at, datetime)

class TestNovelSourceMirror:
    def test_default_values(self):
        mirror = NovelSourceMirror()
        assert mirror.id == 0
        assert mirror.status == "active"
        assert mirror.priority == 0
        assert mirror.failure_count == 0

    def test_custom_values(self):
        mirror = NovelSourceMirror(
            id=1,
            book_id=1,
            source_url="https://example.com",
            source_name="Test Source",
            priority=0,
            status="degraded",
        )
        assert mirror.status == "degraded"
        assert mirror.source_name == "Test Source"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py::TestNovelBook -v
```

Expected: NameError / AttributeError

- [ ] **Step 3: 实现 NovelBook 和 NovelSourceMirror**

在 `app/domain/entities/novel.py` 中，在枚举类之后添加：

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class NovelBook:
    id: int = 0
    book_url: str = ""
    book_name: str = ""
    author: str = ""
    source_name: str = ""
    total_chapters: int = 0
    total_words: int = 0
    status: NovelStatus = field(default=NovelStatus.PENDING)
    source_type: IngestSource = field(default=IngestSource.BOOK_SOURCE)
    ingest_progress: float = 0.0
    ingest_error_msg: Optional[str] = None
    character_count: int = 0
    entity_count: int = 0
    event_count: int = 0
    relationship_count: int = 0
    summary_global: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NovelSourceMirror:
    id: int = 0
    book_id: int = 0
    source_url: str = ""
    source_name: str = ""
    priority: int = 0
    status: str = "active"
    last_check_at: Optional[datetime] = None
    last_check_result: str = ""
    avg_response_ms: int = 0
    failure_count: int = 0
    total_chapters_available: int = 0
    chapters_fetched: int = 0
    content_fingerprint: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py::TestNovelBook tests/test_domain_entities.py::TestNovelSourceMirror -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /workspace/legado-hub && git add -A && git commit -m "feat: add NovelBook and NovelSourceMirror entities"
```

---

### Task 3: NovelChapter + NovelChapterMirror + ChapterFingerprint 实体

**Files:**
- Modify: `app/domain/entities/novel.py`
- Modify: `tests/test_domain_entities.py`

- [ ] **Step 1: 写测试**

在 `tests/test_domain_entities.py` 中添加：

```python
from app.domain.entities.novel import NovelChapter, NovelChapterMirror, ChapterFingerprint

class TestNovelChapter:
    def test_default_canonical(self):
        ch = NovelChapter()
        assert ch.canonical_type == "C"
        assert ch.canonical_num == 0
        assert ch.canonical_full == ""

    def test_character_appearances_is_dict(self):
        ch = NovelChapter(character_appearances={"林远": 5})
        assert ch.character_appearances["林远"] == 5

class TestNovelChapterMirror:
    def test_default_fetch_status(self):
        m = NovelChapterMirror()
        assert m.fetch_status == "pending"

class TestChapterFingerprint:
    def test_default_values(self):
        fp = ChapterFingerprint()
        assert fp.word_count == 0
        assert fp.paragraph_count == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py::TestNovelChapter tests/test_domain_entities.py::TestNovelChapterMirror tests/test_domain_entities.py::TestChapterFingerprint -v
```

Expected: NameError

- [ ] **Step 3: 实现实体**

在 `app/domain/entities/novel.py` 中添加：

```python
@dataclass
class ChapterFingerprint:
    simhash: str = ""
    minhash: str = ""
    word_count: int = 0
    first_30_chars_hash: str = ""
    last_30_chars_hash: str = ""
    paragraph_count: int = 0
    avg_paragraph_len: float = 0.0
    content_hash: str = ""


@dataclass
class NovelChapter:
    id: int = 0
    book_id: int = 0
    canonical_type: str = "C"
    canonical_num: int = 0
    canonical_full: str = ""
    raw_title: str = ""
    parsed_title_core: str = ""
    raw_chapter_num: str = ""
    source_volume: str = ""
    chapter_num: int = 0
    chapter_title: str = ""
    word_count: int = 0
    raw_text_hash: str = ""
    summary: str = ""
    key_events: List[str] = field(default_factory=list)
    character_appearances: Dict[str, int] = field(default_factory=dict)
    location_appearances: Dict[str, int] = field(default_factory=dict)
    mood_tags: List[str] = field(default_factory=list)
    arc_tag: str = ""
    arc_summary: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NovelChapterMirror:
    id: int = 0
    chapter_id: int = 0
    mirror_id: int = 0
    source_url: str = ""
    chapter_num: int = 0
    fetch_status: str = "pending"
    word_count: int = 0
    content_hash: str = ""
    fetch_error: Optional[str] = None
    fetched_at: Optional[datetime] = None
    response_time_ms: int = 0
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py::TestNovelChapter tests/test_domain_entities.py::TestNovelChapterMirror tests/test_domain_entities.py::TestChapterFingerprint -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /workspace/legado-hub && git add -A && git commit -m "feat: add NovelChapter, NovelChapterMirror, ChapterFingerprint entities"
```

---

### Task 4: NovelEntity + NovelRelationship + NovelEvent + NovelStateChange 实体

**Files:**
- Modify: `app/domain/entities/novel.py`
- Modify: `tests/test_domain_entities.py`

- [ ] **Step 1: 写测试**

在 `tests/test_domain_entities.py` 中添加：

```python
from app.domain.entities.novel import NovelEntity, NovelRelationship, NovelEvent, NovelStateChange

class TestNovelEntity:
    def test_default_entity_type(self):
        e = NovelEntity()
        assert e.entity_type == EntityType.CHARACTER
        assert e.importance_score == 3

    def test_attributes_dict(self):
        e = NovelEntity(attributes={"gender": "男", "age": 20})
        assert e.attributes["gender"] == "男"

class TestNovelRelationship:
    def test_default_relation_type(self):
        r = NovelRelationship()
        assert r.relation_type == RelationType.CUSTOM
        assert r.confidence == 0.8

    def test_since_until_chapter(self):
        r = NovelRelationship(since_chapter=10, until_chapter=20)
        assert r.since_chapter == 10
        assert r.until_chapter == 20

class TestNovelEvent:
    def test_default_event_type(self):
        e = NovelEvent()
        assert e.event_type == EventType.CUSTOM
        assert e.importance == 3

    def test_participants_list(self):
        e = NovelEvent(participants=["林远", "周宁"])
        assert "林远" in e.participants

class TestNovelStateChange:
    def test_default_field_name(self):
        sc = NovelStateChange()
        assert sc.field_name == StateField.CUSTOM
        assert sc.confidence == 0.8

    def test_realm_change(self):
        sc = NovelStateChange(
            entity_name="林远",
            field_name=StateField.REALM,
            before_value="炼气期",
            after_value="筑基期",
        )
        assert sc.before_value == "炼气期"
        assert sc.after_value == "筑基期"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py::TestNovelEntity tests/test_domain_entities.py::TestNovelRelationship tests/test_domain_entities.py::TestNovelEvent tests/test_domain_entities.py::TestNovelStateChange -v
```

Expected: NameError

- [ ] **Step 3: 实现实体**

在 `app/domain/entities/novel.py` 中添加：

```python
@dataclass
class NovelEntity:
    id: int = 0
    book_id: int = 0
    name: str = ""
    aliases: List[str] = field(default_factory=list)
    entity_type: EntityType = field(default=EntityType.CHARACTER)
    description: str = ""
    first_appearance_ch: int = 0
    last_appearance_ch: int = 0
    appearance_count: int = 0
    importance_score: int = 3
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NovelRelationship:
    id: int = 0
    book_id: int = 0
    source_entity: str = ""
    target_entity: str = ""
    relation_type: RelationType = field(default=RelationType.CUSTOM)
    description: str = ""
    since_chapter: int = 0
    until_chapter: Optional[int] = None
    confidence: float = 0.8
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NovelEvent:
    id: int = 0
    book_id: int = 0
    chapter_id: int = 0
    chapter_num: int = 0
    event_type: EventType = field(default=EventType.CUSTOM)
    description: str = ""
    participants: List[str] = field(default_factory=list)
    location: str = ""
    importance: int = 3
    related_entities: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NovelStateChange:
    id: int = 0
    book_id: int = 0
    entity_name: str = ""
    chapter_id: int = 0
    chapter_num: int = 0
    field_name: StateField = field(default=StateField.CUSTOM)
    before_value: str = ""
    after_value: str = ""
    trigger_event: str = ""
    confidence: float = 0.8
    created_at: datetime = field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py::TestNovelEntity tests/test_domain_entities.py::TestNovelRelationship tests/test_domain_entities.py::TestNovelEvent tests/test_domain_entities.py::TestNovelStateChange -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
cd /workspace/legado-hub && git add -A && git commit -m "feat: add NovelEntity, NovelRelationship, NovelEvent, NovelStateChange entities"
```

---

### Task 5: 进化相关实体 (EvolutionFeedback, EvolutionRule, PromptTemplate, GepGene)

**Files:**
- Modify: `app/domain/entities/novel.py`
- Modify: `tests/test_domain_entities.py`

- [ ] **Step 1: 写测试**

在 `tests/test_domain_entities.py` 中添加：

```python
from app.domain.entities.novel import EvolutionFeedback, EvolutionRule, PromptTemplate, GepGene

class TestEvolutionFeedback:
    def test_default_values(self):
        ef = EvolutionFeedback()
        assert ef.applied is False
        assert ef.confidence == 1.0

    def test_user_correction(self):
        ef = EvolutionFeedback(
            book_id=1,
            feedback_type="user_correction",
            target_type="entity",
            original_value="林远",
            corrected_value="韩立",
        )
        assert ef.feedback_type == "user_correction"

class TestEvolutionRule:
    def test_default_active(self):
        r = EvolutionRule()
        assert r.active is True
        assert r.hit_count == 0

class TestPromptTemplate:
    def test_default_success_rate(self):
        pt = PromptTemplate()
        assert pt.success_rate == 0.0
        assert pt.version == 1

class TestGepGene:
    def test_default_counters(self):
        g = GepGene()
        assert g.success_count == 0
        assert g.failure_count == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py::TestEvolutionFeedback tests/test_domain_entities.py::TestEvolutionRule tests/test_domain_entities.py::TestPromptTemplate tests/test_domain_entities.py::TestGepGene -v
```

Expected: NameError

- [ ] **Step 3: 实现实体**

在 `app/domain/entities/novel.py` 中添加：

```python
@dataclass
class EvolutionFeedback:
    id: int = 0
    book_id: int = 0
    feedback_type: str = ""
    target_type: str = ""
    target_id: int = 0
    original_value: str = ""
    corrected_value: str = ""
    reason: str = ""
    user_id: Optional[int] = None
    confidence: float = 1.0
    applied: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EvolutionRule:
    id: int = 0
    book_id: int = 0
    rule_type: str = ""
    pattern: str = ""
    replacement: str = ""
    condition: str = ""
    hit_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    active: bool = True
    created_from_feedback_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PromptTemplate:
    id: int = 0
    template_name: str = ""
    version: int = 1
    template_text: str = ""
    success_rate: float = 0.0
    avg_token_usage: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GepGene:
    id: str = ""
    name: str = ""
    trigger_pattern: str = ""
    fix_strategy: str = ""
    code_template: str = ""
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_domain_entities.py::TestEvolutionFeedback tests/test_domain_entities.py::TestEvolutionRule tests/test_domain_entities.py::TestPromptTemplate tests/test_domain_entities.py::TestGepGene -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /workspace/legado-hub && git add -A && git commit -m "feat: add evolution-related entities (EvolutionFeedback, EvolutionRule, PromptTemplate, GepGene)"
```

---

### Task 6: NovelRepository 抽象接口

**Files:**
- Create: `app/domain/repositories/novel_repo.py`
- Modify: `tests/test_novel_repo.py` (接口契约测试)

- [ ] **Step 1: 写接口测试**

```python
# tests/test_novel_repo.py
import pytest
from abc import ABC
from app.domain.repositories.novel_repo import NovelRepository

class TestNovelRepositoryInterface:
    def test_is_abstract(self):
        assert issubclass(NovelRepository, ABC)

    def test_has_required_methods(self):
        required = [
            'save_book', 'get_book', 'get_book_by_url', 'list_books',
            'update_book_status', 'update_book_summary', 'delete_book',
            'save_chapter', 'save_chapters_batch', 'get_chapter',
            'get_chapters_by_book', 'update_chapter_summary',
            'save_entity', 'save_entities_batch', 'get_entity_by_name',
            'list_entities', 'search_entities',
            'save_relationship', 'save_relationships_batch', 'get_relationships',
            'save_event', 'save_events_batch', 'get_events',
            'save_state_change', 'save_state_changes_batch', 'get_state_changes',
        ]
        for method in required:
            assert hasattr(NovelRepository, method), f"Missing {method}"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_novel_repo.py::TestNovelRepositoryInterface -v
```

Expected: ImportError

- [ ] **Step 3: 实现接口**

```python
# app/domain/repositories/novel_repo.py
from abc import ABC, abstractmethod
from typing import List, Optional

from ..entities.novel import (
    NovelBook, NovelChapter, NovelEntity, NovelRelationship,
    NovelEvent, NovelStateChange, NovelStatus, EntityType, EventType, StateField
)


class NovelRepository(ABC):
    # --- NovelBook ---
    @abstractmethod
    async def save_book(self, book: NovelBook) -> NovelBook: ...

    @abstractmethod
    async def get_book(self, book_id: int) -> Optional[NovelBook]: ...

    @abstractmethod
    async def get_book_by_url(self, book_url: str) -> Optional[NovelBook]: ...

    @abstractmethod
    async def list_books(self, status: Optional[NovelStatus] = None, limit: int = 20, offset: int = 0) -> List[NovelBook]: ...

    @abstractmethod
    async def update_book_status(self, book_id: int, status: NovelStatus, progress: Optional[float] = None, error_msg: Optional[str] = None) -> bool: ...

    @abstractmethod
    async def update_book_summary(self, book_id: int, summary: str) -> bool: ...

    @abstractmethod
    async def delete_book(self, book_id: int) -> bool: ...

    # --- NovelChapter ---
    @abstractmethod
    async def save_chapter(self, chapter: NovelChapter) -> NovelChapter: ...

    @abstractmethod
    async def save_chapters_batch(self, chapters: List[NovelChapter]) -> int: ...

    @abstractmethod
    async def get_chapter(self, chapter_id: int) -> Optional[NovelChapter]: ...

    @abstractmethod
    async def get_chapters_by_book(self, book_id: int, start_num: int = 1, end_num: Optional[int] = None) -> List[NovelChapter]: ...

    @abstractmethod
    async def update_chapter_summary(self, chapter_id: int, summary: str, key_events: List[str]) -> bool: ...

    # --- NovelEntity ---
    @abstractmethod
    async def save_entity(self, entity: NovelEntity) -> NovelEntity: ...

    @abstractmethod
    async def save_entities_batch(self, entities: List[NovelEntity]) -> int: ...

    @abstractmethod
    async def get_entity(self, entity_id: int) -> Optional[NovelEntity]: ...

    @abstractmethod
    async def get_entity_by_name(self, book_id: int, name: str) -> Optional[NovelEntity]: ...

    @abstractmethod
    async def list_entities(self, book_id: int, entity_type: Optional[EntityType] = None, limit: int = 50, offset: int = 0) -> List[NovelEntity]: ...

    @abstractmethod
    async def search_entities(self, book_id: int, keyword: str, entity_type: Optional[EntityType] = None, limit: int = 20) -> List[NovelEntity]: ...

    # --- NovelRelationship ---
    @abstractmethod
    async def save_relationship(self, rel: NovelRelationship) -> NovelRelationship: ...

    @abstractmethod
    async def save_relationships_batch(self, rels: List[NovelRelationship]) -> int: ...

    @abstractmethod
    async def get_relationships(self, book_id: int, entity_name: Optional[str] = None, limit: int = 50) -> List[NovelRelationship]: ...

    # --- NovelEvent ---
    @abstractmethod
    async def save_event(self, event: NovelEvent) -> NovelEvent: ...

    @abstractmethod
    async def save_events_batch(self, events: List[NovelEvent]) -> int: ...

    @abstractmethod
    async def get_events(self, book_id: int, chapter_num: Optional[int] = None, event_type: Optional[EventType] = None, min_importance: int = 1, limit: int = 50) -> List[NovelEvent]: ...

    # --- NovelStateChange ---
    @abstractmethod
    async def save_state_change(self, sc: NovelStateChange) -> NovelStateChange: ...

    @abstractmethod
    async def save_state_changes_batch(self, scs: List[NovelStateChange]) -> int: ...

    @abstractmethod
    async def get_state_changes(self, book_id: int, entity_name: Optional[str] = None, field_name: Optional[StateField] = None, limit: int = 50) -> List[NovelStateChange]: ...
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_novel_repo.py::TestNovelRepositoryInterface -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /workspace/legado-hub && git add -A && git commit -m "feat: add NovelRepository abstract interface"
```

---

### Task 7: 数据库 Schema 迁移脚本

**Files:**
- Create: `app/database_migrations/novel_schema.sql`

- [ ] **Step 1: 创建迁移脚本**

```sql
-- app/database_migrations/novel_schema.sql
-- NovelUnderstanding 系统数据库 Schema

-- novels: 小说索引
CREATE TABLE IF NOT EXISTS novels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_url TEXT NOT NULL UNIQUE,
    book_name TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    source_name TEXT NOT NULL DEFAULT '',
    total_chapters INTEGER NOT NULL DEFAULT 0,
    total_words INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    source_type TEXT NOT NULL DEFAULT 'book_source',
    ingest_progress REAL NOT NULL DEFAULT 0.0,
    ingest_error_msg TEXT,
    character_count INTEGER NOT NULL DEFAULT 0,
    entity_count INTEGER NOT NULL DEFAULT 0,
    event_count INTEGER NOT NULL DEFAULT 0,
    relationship_count INTEGER NOT NULL DEFAULT 0,
    summary_global TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_novels_status ON novels(status);

-- novel_source_mirrors: 书源镜像
CREATE TABLE IF NOT EXISTS novel_source_mirrors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    source_name TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    last_check_at TIMESTAMP,
    last_check_result TEXT NOT NULL DEFAULT '',
    avg_response_ms INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    total_chapters_available INTEGER NOT NULL DEFAULT 0,
    chapters_fetched INTEGER NOT NULL DEFAULT 0,
    content_fingerprint TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(book_id, source_url)
);
CREATE INDEX IF NOT EXISTS idx_mirrors_book_status ON novel_source_mirrors(book_id, status);

-- novel_chapters: 章节元数据
CREATE TABLE IF NOT EXISTS novel_chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    canonical_type TEXT NOT NULL DEFAULT 'C',
    canonical_num INTEGER NOT NULL DEFAULT 0,
    canonical_full TEXT NOT NULL DEFAULT '',
    raw_title TEXT NOT NULL DEFAULT '',
    parsed_title_core TEXT NOT NULL DEFAULT '',
    raw_chapter_num TEXT NOT NULL DEFAULT '',
    source_volume TEXT NOT NULL DEFAULT '',
    chapter_num INTEGER NOT NULL DEFAULT 0,
    chapter_title TEXT NOT NULL DEFAULT '',
    word_count INTEGER NOT NULL DEFAULT 0,
    raw_text_hash TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    key_events TEXT NOT NULL DEFAULT '[]',
    character_appearances TEXT NOT NULL DEFAULT '{}',
    location_appearances TEXT NOT NULL DEFAULT '{}',
    mood_tags TEXT NOT NULL DEFAULT '[]',
    arc_tag TEXT NOT NULL DEFAULT '',
    arc_summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(book_id, canonical_full)
);
CREATE INDEX IF NOT EXISTS idx_chapters_book_canonical ON novel_chapters(book_id, canonical_type, canonical_num);

-- novel_chapter_mirrors: 章节镜像
CREATE TABLE IF NOT EXISTS novel_chapter_mirrors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    mirror_id INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    fetch_status TEXT NOT NULL DEFAULT 'pending',
    word_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    fetch_error TEXT,
    fetched_at TIMESTAMP,
    response_time_ms INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (chapter_id) REFERENCES novel_chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (mirror_id) REFERENCES novel_source_mirrors(id) ON DELETE CASCADE,
    UNIQUE(chapter_id, mirror_id)
);

-- novel_entities: 实体
CREATE TABLE IF NOT EXISTS novel_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    entity_type TEXT NOT NULL DEFAULT 'character',
    description TEXT NOT NULL DEFAULT '',
    first_appearance_ch INTEGER NOT NULL DEFAULT 0,
    last_appearance_ch INTEGER NOT NULL DEFAULT 0,
    appearance_count INTEGER NOT NULL DEFAULT 0,
    importance_score INTEGER NOT NULL DEFAULT 3,
    attributes TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(book_id, name)
);
CREATE INDEX IF NOT EXISTS idx_entities_book_type ON novel_entities(book_id, entity_type);

-- novel_relationships: 关系
CREATE TABLE IF NOT EXISTS novel_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    source_entity TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'custom',
    description TEXT NOT NULL DEFAULT '',
    since_chapter INTEGER NOT NULL DEFAULT 0,
    until_chapter INTEGER,
    confidence REAL NOT NULL DEFAULT 0.8,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rels_source ON novel_relationships(book_id, source_entity);

-- novel_events: 事件
CREATE TABLE IF NOT EXISTS novel_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    chapter_num INTEGER NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'custom',
    description TEXT NOT NULL DEFAULT '',
    participants TEXT NOT NULL DEFAULT '[]',
    location TEXT NOT NULL DEFAULT '',
    importance INTEGER NOT NULL DEFAULT 3,
    related_entities TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_events_book_ch ON novel_events(book_id, chapter_num);
CREATE INDEX IF NOT EXISTS idx_events_importance ON novel_events(book_id, importance DESC);

-- novel_state_changes: 状态变迁
CREATE TABLE IF NOT EXISTS novel_state_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    entity_name TEXT NOT NULL,
    chapter_id INTEGER NOT NULL,
    chapter_num INTEGER NOT NULL,
    field_name TEXT NOT NULL DEFAULT 'custom',
    before_value TEXT NOT NULL DEFAULT '',
    after_value TEXT NOT NULL DEFAULT '',
    trigger_event TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.8,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sc_book_entity ON novel_state_changes(book_id, entity_name);

-- evolution_feedbacks: 反馈记录
CREATE TABLE IF NOT EXISTS evolution_feedbacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    feedback_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    original_value TEXT NOT NULL DEFAULT '',
    corrected_value TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    confidence REAL NOT NULL DEFAULT 1.0,
    applied BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_feedback_book ON evolution_feedbacks(book_id, target_type);

-- evolution_rules: 进化规则
CREATE TABLE IF NOT EXISTS evolution_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL DEFAULT 0,
    rule_type TEXT NOT NULL,
    pattern TEXT NOT NULL,
    replacement TEXT NOT NULL DEFAULT '',
    condition TEXT NOT NULL DEFAULT '{}',
    hit_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_from_feedback_id INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rules_book ON evolution_rules(book_id, rule_type, active);

-- prompt_templates: Prompt版本管理
CREATE TABLE IF NOT EXISTS prompt_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    template_text TEXT NOT NULL,
    success_rate REAL NOT NULL DEFAULT 0.0,
    avg_token_usage INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(template_name, version)
);
```

- [ ] **Step 2: 验证 SQL 语法**

```bash
cd /workspace/legado-hub/backend && python -c "
import sqlite3
with open('app/database_migrations/novel_schema.sql') as f:
    sql = f.read()
conn = sqlite3.connect(':memory:')
conn.executescript(sql)
print('Schema validated successfully')
conn.close()
"
```

Expected: `Schema validated successfully`

- [ ] **Step 3: Commit**

```bash
cd /workspace/legado-hub && git add -A && git commit -m "feat: add novel schema migration SQL"
```

---

### Task 8: SQLite 仓储实现

**Files:**
- Create: `app/infrastructure/persistence/sqlite/novel_repo_impl.py`
- Modify: `tests/test_novel_repo.py`

- [ ] **Step 1: 写集成测试**

```python
# tests/test_novel_repo.py
import pytest
import aiosqlite
from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
from app.domain.entities.novel import NovelBook, NovelChapter, NovelEntity, NovelStatus, EntityType

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def repo():
    db = await aiosqlite.connect(":memory:")
    with open("app/database_migrations/novel_schema.sql") as f:
        await db.executescript(f.read())
    repo = SqliteNovelRepository(db)
    yield repo
    await db.close()

class TestSqliteNovelRepository:
    async def test_save_and_get_book(self, repo):
        book = NovelBook(book_url="https://test.com", book_name="Test", author="A")
        saved = await repo.save_book(book)
        assert saved.id > 0

        fetched = await repo.get_book(saved.id)
        assert fetched is not None
        assert fetched.book_name == "Test"

    async def test_get_book_by_url(self, repo):
        await repo.save_book(NovelBook(book_url="https://unique.com", book_name="U"))
        fetched = await repo.get_book_by_url("https://unique.com")
        assert fetched is not None
        assert fetched.book_name == "U"

    async def test_list_books_by_status(self, repo):
        await repo.save_book(NovelBook(book_url="https://a.com", status=NovelStatus.READY))
        await repo.save_book(NovelBook(book_url="https://b.com", status=NovelStatus.PENDING))
        results = await repo.list_books(status=NovelStatus.READY)
        assert len(results) == 1
        assert results[0].book_url == "https://a.com"

    async def test_update_book_status(self, repo):
        saved = await repo.save_book(NovelBook(book_url="https://c.com"))
        result = await repo.update_book_status(saved.id, NovelStatus.INGESTING, progress=0.5)
        assert result is True
        fetched = await repo.get_book(saved.id)
        assert fetched.status == NovelStatus.INGESTING
        assert fetched.ingest_progress == 0.5

    async def test_save_and_get_chapter(self, repo):
        book = await repo.save_book(NovelBook(book_url="https://d.com"))
        ch = NovelChapter(book_id=book.id, canonical_full="C1", chapter_title="第一章")
        saved = await repo.save_chapter(ch)
        assert saved.id > 0

        fetched = await repo.get_chapter(saved.id)
        assert fetched.chapter_title == "第一章"

    async def test_save_entities_batch(self, repo):
        book = await repo.save_book(NovelBook(book_url="https://e.com"))
        entities = [
            NovelEntity(book_id=book.id, name="林远", entity_type=EntityType.CHARACTER),
            NovelEntity(book_id=book.id, name="周宁", entity_type=EntityType.CHARACTER),
        ]
        count = await repo.save_entities_batch(entities)
        assert count == 2

        results = await repo.list_entities(book.id)
        assert len(results) == 2
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_novel_repo.py::TestSqliteNovelRepository -v
```

Expected: ImportError / ModuleNotFoundError

- [ ] **Step 3: 实现 SQLite 仓储**

```python
# app/infrastructure/persistence/sqlite/novel_repo_impl.py
import json
import aiosqlite
from typing import List, Optional

from app.domain.repositories.novel_repo import NovelRepository
from app.domain.entities.novel import (
    NovelBook, NovelChapter, NovelChapterMirror, ChapterFingerprint,
    NovelEntity, NovelRelationship, NovelEvent, NovelStateChange,
    NovelStatus, EntityType, EventType, StateField, RelationType,
    NovelSourceMirror,
)


class SqliteNovelRepository(NovelRepository):
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # --- NovelBook ---
    async def save_book(self, book: NovelBook) -> NovelBook:
        cursor = await self._db.execute(
            """INSERT INTO novels (book_url, book_name, author, source_name, total_chapters, total_words,
                status, source_type, ingest_progress, ingest_error_msg, summary_global)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_url) DO UPDATE SET
                book_name=excluded.book_name, author=excluded.author,
                source_name=excluded.source_name, total_chapters=excluded.total_chapters,
                total_words=excluded.total_words, status=excluded.status,
                source_type=excluded.source_type, ingest_progress=excluded.ingest_progress,
                ingest_error_msg=excluded.ingest_error_msg, summary_global=excluded.summary_global,
                updated_at=CURRENT_TIMESTAMP""",
            (book.book_url, book.book_name, book.author, book.source_name,
             book.total_chapters, book.total_words, book.status.value, book.source_type.value,
             book.ingest_progress, book.ingest_error_msg, book.summary_global)
        )
        await self._db.commit()
        book.id = cursor.lastrowid
        return book

    async def get_book(self, book_id: int) -> Optional[NovelBook]:
        async with self._db.execute("SELECT * FROM novels WHERE id=?", (book_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_book(row)
        return None

    async def get_book_by_url(self, book_url: str) -> Optional[NovelBook]:
        async with self._db.execute("SELECT * FROM novels WHERE book_url=?", (book_url,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_book(row)
        return None

    async def list_books(self, status: Optional[NovelStatus] = None, limit: int = 20, offset: int = 0) -> List[NovelBook]:
        if status:
            async with self._db.execute("SELECT * FROM novels WHERE status=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                                        (status.value, limit, offset)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._db.execute("SELECT * FROM novels ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                                        (limit, offset)) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_book(r) for r in rows]

    async def update_book_status(self, book_id: int, status: NovelStatus, progress: Optional[float] = None, error_msg: Optional[str] = None) -> bool:
        fields = ["status=?"]
        params = [status.value]
        if progress is not None:
            fields.append("ingest_progress=?")
            params.append(progress)
        if error_msg is not None:
            fields.append("ingest_error_msg=?")
            params.append(error_msg)
        params.append(book_id)
        await self._db.execute(f"UPDATE novels SET {', '.join(fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", params)
        await self._db.commit()
        return True

    async def update_book_summary(self, book_id: int, summary: str) -> bool:
        await self._db.execute("UPDATE novels SET summary_global=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                               (summary, book_id))
        await self._db.commit()
        return True

    async def delete_book(self, book_id: int) -> bool:
        await self._db.execute("DELETE FROM novels WHERE id=?", (book_id,))
        await self._db.commit()
        return True

    # --- NovelChapter ---
    async def save_chapter(self, chapter: NovelChapter) -> NovelChapter:
        cursor = await self._db.execute(
            """INSERT INTO novel_chapters (book_id, canonical_type, canonical_num, canonical_full,
                raw_title, parsed_title_core, raw_chapter_num, source_volume, chapter_num, chapter_title,
                word_count, raw_text_hash, summary, key_events, character_appearances,
                location_appearances, mood_tags, arc_tag, arc_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (chapter.book_id, chapter.canonical_type, chapter.canonical_num, chapter.canonical_full,
             chapter.raw_title, chapter.parsed_title_core, chapter.raw_chapter_num, chapter.source_volume,
             chapter.chapter_num, chapter.chapter_title, chapter.word_count, chapter.raw_text_hash,
             chapter.summary, json.dumps(chapter.key_events, ensure_ascii=False),
             json.dumps(chapter.character_appearances, ensure_ascii=False),
             json.dumps(chapter.location_appearances, ensure_ascii=False),
             json.dumps(chapter.mood_tags, ensure_ascii=False),
             chapter.arc_tag, chapter.arc_summary)
        )
        await self._db.commit()
        chapter.id = cursor.lastrowid
        return chapter

    async def save_chapters_batch(self, chapters: List[NovelChapter]) -> int:
        for ch in chapters:
            await self.save_chapter(ch)
        return len(chapters)

    async def get_chapter(self, chapter_id: int) -> Optional[NovelChapter]:
        async with self._db.execute("SELECT * FROM novel_chapters WHERE id=?", (chapter_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_chapter(row)
        return None

    async def get_chapters_by_book(self, book_id: int, start_num: int = 1, end_num: Optional[int] = None) -> List[NovelChapter]:
        if end_num:
            async with self._db.execute(
                "SELECT * FROM novel_chapters WHERE book_id=? AND canonical_num >= ? AND canonical_num <= ? ORDER BY canonical_num",
                (book_id, start_num, end_num)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._db.execute(
                "SELECT * FROM novel_chapters WHERE book_id=? AND canonical_num >= ? ORDER BY canonical_num",
                (book_id, start_num)) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_chapter(r) for r in rows]

    async def update_chapter_summary(self, chapter_id: int, summary: str, key_events: List[str]) -> bool:
        await self._db.execute(
            "UPDATE novel_chapters SET summary=?, key_events=? WHERE id=?",
            (summary, json.dumps(key_events, ensure_ascii=False), chapter_id))
        await self._db.commit()
        return True

    # --- NovelEntity ---
    async def save_entity(self, entity: NovelEntity) -> NovelEntity:
        cursor = await self._db.execute(
            """INSERT INTO novel_entities (book_id, name, aliases, entity_type, description,
                first_appearance_ch, last_appearance_ch, appearance_count, importance_score, attributes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id, name) DO UPDATE SET
                aliases=excluded.aliases, entity_type=excluded.entity_type,
                description=excluded.description, first_appearance_ch=excluded.first_appearance_ch,
                last_appearance_ch=excluded.last_appearance_ch, appearance_count=excluded.appearance_count,
                importance_score=excluded.importance_score, attributes=excluded.attributes""",
            (entity.book_id, entity.name, json.dumps(entity.aliases, ensure_ascii=False),
             entity.entity_type.value, entity.description, entity.first_appearance_ch,
             entity.last_appearance_ch, entity.appearance_count, entity.importance_score,
             json.dumps(entity.attributes, ensure_ascii=False))
        )
        await self._db.commit()
        if entity.id == 0:
            entity.id = cursor.lastrowid
        return entity

    async def save_entities_batch(self, entities: List[NovelEntity]) -> int:
        for e in entities:
            await self.save_entity(e)
        return len(entities)

    async def get_entity(self, entity_id: int) -> Optional[NovelEntity]:
        async with self._db.execute("SELECT * FROM novel_entities WHERE id=?", (entity_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_entity(row)
        return None

    async def get_entity_by_name(self, book_id: int, name: str) -> Optional[NovelEntity]:
        async with self._db.execute("SELECT * FROM novel_entities WHERE book_id=? AND name=?", (book_id, name)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_entity(row)
        return None

    async def list_entities(self, book_id: int, entity_type: Optional[EntityType] = None, limit: int = 50, offset: int = 0) -> List[NovelEntity]:
        if entity_type:
            async with self._db.execute(
                "SELECT * FROM novel_entities WHERE book_id=? AND entity_type=? ORDER BY importance_score DESC LIMIT ? OFFSET ?",
                (book_id, entity_type.value, limit, offset)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._db.execute(
                "SELECT * FROM novel_entities WHERE book_id=? ORDER BY importance_score DESC LIMIT ? OFFSET ?",
                (book_id, limit, offset)) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_entity(r) for r in rows]

    async def search_entities(self, book_id: int, keyword: str, entity_type: Optional[EntityType] = None, limit: int = 20) -> List[NovelEntity]:
        # 简单 LIKE 搜索，后续可用 FTS5
        pattern = f"%{keyword}%"
        if entity_type:
            async with self._db.execute(
                "SELECT * FROM novel_entities WHERE book_id=? AND entity_type=? AND (name LIKE ? OR description LIKE ?) LIMIT ?",
                (book_id, entity_type.value, pattern, pattern, limit)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._db.execute(
                "SELECT * FROM novel_entities WHERE book_id=? AND (name LIKE ? OR description LIKE ?) LIMIT ?",
                (book_id, pattern, pattern, limit)) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_entity(r) for r in rows]

    # --- NovelRelationship ---
    async def save_relationship(self, rel: NovelRelationship) -> NovelRelationship:
        cursor = await self._db.execute(
            """INSERT INTO novel_relationships (book_id, source_entity, target_entity, relation_type,
                description, since_chapter, until_chapter, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (rel.book_id, rel.source_entity, rel.target_entity, rel.relation_type.value,
             rel.description, rel.since_chapter, rel.until_chapter, rel.confidence)
        )
        await self._db.commit()
        rel.id = cursor.lastrowid
        return rel

    async def save_relationships_batch(self, rels: List[NovelRelationship]) -> int:
        for r in rels:
            await self.save_relationship(r)
        return len(rels)

    async def get_relationships(self, book_id: int, entity_name: Optional[str] = None, limit: int = 50) -> List[NovelRelationship]:
        if entity_name:
            async with self._db.execute(
                """SELECT * FROM novel_relationships WHERE book_id=? 
                    AND (source_entity=? OR target_entity=?) LIMIT ?""",
                (book_id, entity_name, entity_name, limit)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._db.execute(
                "SELECT * FROM novel_relationships WHERE book_id=? LIMIT ?",
                (book_id, limit)) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_relationship(r) for r in rows]

    # --- NovelEvent ---
    async def save_event(self, event: NovelEvent) -> NovelEvent:
        cursor = await self._db.execute(
            """INSERT INTO novel_events (book_id, chapter_id, chapter_num, event_type, description,
                participants, location, importance, related_entities)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.book_id, event.chapter_id, event.chapter_num, event.event_type.value,
             event.description, json.dumps(event.participants, ensure_ascii=False),
             event.location, event.importance,
             json.dumps(event.related_entities, ensure_ascii=False))
        )
        await self._db.commit()
        event.id = cursor.lastrowid
        return event

    async def save_events_batch(self, events: List[NovelEvent]) -> int:
        for e in events:
            await self.save_event(e)
        return len(events)

    async def get_events(self, book_id: int, chapter_num: Optional[int] = None, event_type: Optional[EventType] = None, min_importance: int = 1, limit: int = 50) -> List[NovelEvent]:
        conditions = ["book_id=?"]
        params = [book_id]
        if chapter_num is not None:
            conditions.append("chapter_num=?")
            params.append(chapter_num)
        if event_type is not None:
            conditions.append("event_type=?")
            params.append(event_type.value)
        conditions.append("importance>=?")
        params.append(min_importance)
        params.append(limit)

        query = f"SELECT * FROM novel_events WHERE {' AND '.join(conditions)} ORDER BY importance DESC LIMIT ?"
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    # --- NovelStateChange ---
    async def save_state_change(self, sc: NovelStateChange) -> NovelStateChange:
        cursor = await self._db.execute(
            """INSERT INTO novel_state_changes (book_id, entity_name, chapter_id, chapter_num,
                field_name, before_value, after_value, trigger_event, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sc.book_id, sc.entity_name, sc.chapter_id, sc.chapter_num,
             sc.field_name.value, sc.before_value, sc.after_value, sc.trigger_event, sc.confidence)
        )
        await self._db.commit()
        sc.id = cursor.lastrowid
        return sc

    async def save_state_changes_batch(self, scs: List[NovelStateChange]) -> int:
        for sc in scs:
            await self.save_state_change(sc)
        return len(scs)

    async def get_state_changes(self, book_id: int, entity_name: Optional[str] = None, field_name: Optional[StateField] = None, limit: int = 50) -> List[NovelStateChange]:
        conditions = ["book_id=?"]
        params = [book_id]
        if entity_name:
            conditions.append("entity_name=?")
            params.append(entity_name)
        if field_name:
            conditions.append("field_name=?")
            params.append(field_name.value)
        params.append(limit)

        query = f"SELECT * FROM novel_state_changes WHERE {' AND '.join(conditions)} ORDER BY chapter_num DESC LIMIT ?"
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_state_change(r) for r in rows]

    # --- Row converters ---
    def _row_to_book(self, row: aiosqlite.Row) -> NovelBook:
        return NovelBook(
            id=row[0], book_url=row[1], book_name=row[2], author=row[3],
            source_name=row[4], total_chapters=row[5], total_words=row[6],
            status=NovelStatus(row[7]), source_type=IngestSource(row[8]),
            ingest_progress=row[9], ingest_error_msg=row[10],
            character_count=row[11], entity_count=row[12], event_count=row[13],
            relationship_count=row[14], summary_global=row[15],
            created_at=row[16], updated_at=row[17]
        )

    def _row_to_chapter(self, row: aiosqlite.Row) -> NovelChapter:
        return NovelChapter(
            id=row[0], book_id=row[1], canonical_type=row[2], canonical_num=row[3],
            canonical_full=row[4], raw_title=row[5], parsed_title_core=row[6],
            raw_chapter_num=row[7], source_volume=row[8], chapter_num=row[9],
            chapter_title=row[10], word_count=row[11], raw_text_hash=row[12],
            summary=row[13], key_events=json.loads(row[14]),
            character_appearances=json.loads(row[15]),
            location_appearances=json.loads(row[16]),
            mood_tags=json.loads(row[17]), arc_tag=row[18], arc_summary=row[19],
            created_at=row[20]
        )

    def _row_to_entity(self, row: aiosqlite.Row) -> NovelEntity:
        return NovelEntity(
            id=row[0], book_id=row[1], name=row[2], aliases=json.loads(row[3]),
            entity_type=EntityType(row[4]), description=row[5],
            first_appearance_ch=row[6], last_appearance_ch=row[7],
            appearance_count=row[8], importance_score=row[9],
            attributes=json.loads(row[10]), created_at=row[11]
        )

    def _row_to_relationship(self, row: aiosqlite.Row) -> NovelRelationship:
        return NovelRelationship(
            id=row[0], book_id=row[1], source_entity=row[2], target_entity=row[3],
            relation_type=RelationType(row[4]), description=row[5],
            since_chapter=row[6], until_chapter=row[7], confidence=row[8],
            created_at=row[9]
        )

    def _row_to_event(self, row: aiosqlite.Row) -> NovelEvent:
        return NovelEvent(
            id=row[0], book_id=row[1], chapter_id=row[2], chapter_num=row[3],
            event_type=EventType(row[4]), description=row[5],
            participants=json.loads(row[6]), location=row[7],
            importance=row[8], related_entities=json.loads(row[9]),
            created_at=row[10]
        )

    def _row_to_state_change(self, row: aiosqlite.Row) -> NovelStateChange:
        return NovelStateChange(
            id=row[0], book_id=row[1], entity_name=row[2], chapter_id=row[3],
            chapter_num=row[4], field_name=StateField(row[5]),
            before_value=row[6], after_value=row[7], trigger_event=row[8],
            confidence=row[9], created_at=row[10]
        )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /workspace/legado-hub/backend && python -m pytest tests/test_novel_repo.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd /workspace/legado-hub && git add -A && git commit -m "feat: add SqliteNovelRepository implementation"
```

---

### Task 9: 运行全部测试确认无回归

- [ ] **Step 1: 运行全部测试**

```bash
cd /workspace/legado-hub/backend && python -m pytest --tb=short -q
```

Expected: 现有 529+ 测试全部通过，新增 23+ 测试全部通过

- [ ] **Step 2: 如有失败，修复后再 commit**

---

## Phase 1 完成标准

- [ ] 所有 6 个枚举类定义完成并通过测试
- [ ] 所有 13 个 dataclass 实体定义完成并通过测试
- [ ] `NovelRepository` 抽象接口定义完成并通过测试
- [ ] SQLite Schema 验证通过
- [ ] `SqliteNovelRepository` 实现完成并通过集成测试
- [ ] 全部现有 529+ 测试无回归
