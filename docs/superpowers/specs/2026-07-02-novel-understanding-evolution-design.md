# NovelUnderstanding 自主进化引擎 — 设计规格书

> 版本: v1.0  
> 日期: 2026-07-02  
> 状态: 已批准  
> 融合架构: Hermes Agent (Skill沉淀 + 闭环学习) + OpenClaw Evolver (代码自修复 + GEP基因协议) + 分层记忆 + RAG检索

---

## 一、背景与目标

### 1.1 问题陈述

现有 LegadoHub Pro 的 6 个 AI 分析端点（人物关系/世界观/剧情时间线/问答/修复/审查）存在根本缺陷：**LLM 只能看到用户传入的 3000 字截断文本**，无法真正理解整部小说的角色网络、世界观设定和剧情走向。这导致：

- 人物关系提取只能看到片段，遗漏跨章节的隐性关系
- 世界观分析基于碎片化文本，无法构建完整的势力分布和规则体系
- 剧情时间线依赖前 20 章原文，无法追踪长篇网文（1000+ 章）的完整脉络
- 智能问答无法回答"这个角色在第 300 章说过什么"之类的问题

### 1.2 核心目标

构建一个 **NovelUnderstanding 自主进化引擎**，具备以下能力：

1. **深度理解**：从书源在线获取或用户上传全文，构建包含角色/关系/事件/状态变迁的知识图谱
2. **Token 节约**：通过分层摘要 + BM25/向量/图谱三路 RAG，将 LLM 分析时的上下文控制在 4000-5000 token
3. **多书源容错**：支持同一本书的多个书源镜像，自动处理失效/缺失/冲突
4. **章节标准化**：跨书源建立统一的 canonical 章节编号，解决分卷/合并/番外等差异
5. **自主进化**：借鉴 Hermes Agent 的 Skill 沉淀 + 闭环学习，以及 OpenClaw Evolver 的代码自修复 + GEP 基因协议，让系统越用越强

---

## 二、DDD 领域模型

### 2.1 枚举类

```python
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

### 2.2 核心实体

```python
@dataclass
class NovelBook:
    id: int = 0
    book_url: str = ""            # 唯一标识
    book_name: str = ""
    author: str = ""
    source_name: str = ""
    total_chapters: int = 0
    total_words: int = 0
    status: NovelStatus = NovelStatus.PENDING
    source_type: IngestSource = IngestSource.BOOK_SOURCE
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
    status: str = "active"        # active / degraded / failed / disabled
    last_check_at: Optional[datetime] = None
    last_check_result: str = ""
    avg_response_ms: int = 0
    failure_count: int = 0
    total_chapters_available: int = 0
    chapters_fetched: int = 0
    content_fingerprint: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class NovelChapter:
    id: int = 0
    book_id: int = 0
    canonical_type: str = "C"     # C/P/E/X/V
    canonical_num: int = 0
    canonical_full: str = "C1"
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
class NovelEntity:
    id: int = 0
    book_id: int = 0
    name: str = ""
    aliases: List[str] = field(default_factory=list)
    entity_type: EntityType = EntityType.CHARACTER
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
    relation_type: RelationType = RelationType.CUSTOM
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
    event_type: EventType = EventType.CUSTOM
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
    field_name: StateField = StateField.CUSTOM
    before_value: str = ""
    after_value: str = ""
    trigger_event: str = ""
    confidence: float = 0.8
    created_at: datetime = field(default_factory=datetime.utcnow)
```

### 2.3 进化相关实体

```python
@dataclass
class EvolutionFeedback:
    id: int = 0
    book_id: int = 0
    feedback_type: str = ""       # user_correction / self_detected / consistency_error
    target_type: str = ""         # entity / relationship / event / summary / alignment
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

---

## 三、数据库 Schema

### 3.1 主表

```sql
-- novels
CREATE TABLE novels (
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
CREATE INDEX idx_novels_status ON novels(status);

-- novel_source_mirrors
CREATE TABLE novel_source_mirrors (
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
CREATE INDEX idx_mirrors_book_status ON novel_source_mirrors(book_id, status);

-- novel_chapters
CREATE TABLE novel_chapters (
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
CREATE INDEX idx_chapters_book_canonical ON novel_chapters(book_id, canonical_type, canonical_num);

-- novel_chapter_mirrors
CREATE TABLE novel_chapter_mirrors (
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

-- novel_entities
CREATE TABLE novel_entities (
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
CREATE INDEX idx_entities_book_type ON novel_entities(book_id, entity_type);
CREATE VIRTUAL TABLE novel_entities_fts USING fts5(name, aliases, description, content='novel_entities', content_rowid='id');

-- novel_relationships
CREATE TABLE novel_relationships (
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
CREATE INDEX idx_rels_source ON novel_relationships(book_id, source_entity);

-- novel_events
CREATE TABLE novel_events (
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
CREATE INDEX idx_events_book_ch ON novel_events(book_id, chapter_num);
CREATE INDEX idx_events_importance ON novel_events(book_id, importance DESC);

-- novel_state_changes
CREATE TABLE novel_state_changes (
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
CREATE INDEX idx_sc_book_entity ON novel_state_changes(book_id, entity_name);
```

### 3.2 进化相关表

```sql
-- evolution_feedbacks
CREATE TABLE evolution_feedbacks (
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
CREATE INDEX idx_feedback_book ON evolution_feedbacks(book_id, target_type);

-- evolution_rules
CREATE TABLE evolution_rules (
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
CREATE INDEX idx_rules_book ON evolution_rules(book_id, rule_type, active);

-- prompt_templates
CREATE TABLE prompt_templates (
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

---

## 四、章节标准化与跨书源映射

### 4.1 标题解析器

支持阿拉伯数字、中文数字、分卷格式、特殊章节（楔子/番外/后记）的自动识别和标准化。

```python
class ChapterTitleParser:
    PATTERNS = {
        'arabic': re.compile(r'(?:第|Chapter\s+|Ch\.?\s*)(\d+)(?:章|:\s*|[-\s])?\s*'),
        'chinese': re.compile(r'第([零一二三四五六七八九十百千万亿\d]+)章\s*'),
        'split': re.compile(r'(?:第)(\d+)(?:章)[（(]?(上|中|下|之一|之二|1|2|3)?[）)]?\s*'),
        'volume': re.compile(r'(?:第([一二三四五六七八九十\d]+)卷|卷([一二三四五六七八九十\d]+)|Vol\.?\s*(\d+))\s*[·\s]?\s*(?:第(\d+)章|Chapter\s+(\d+))'),
        'prologue': re.compile(r'^(楔子|前言|引子|序章|序幕|开篇|写在前面)'),
        'epilogue': re.compile(r'^(后记|尾声|大结局|终章|完结篇|结束语)'),
        'extra': re.compile(r'^(番外|外传|特别篇|附录|小剧场|if线|平行世界)'),
    }
```

### 4.2 标准化编号规则

| 原始类型 | 示例 | canonical_type | canonical_num | canonical_full |
|---------|------|---------------|---------------|----------------|
| 楔子 | 楔子 | P | 0 | P0 |
| 正文 | 第1章 | C | 1 | C1 |
| 番外 | 番外一 | X | 1 | X1 |
| 后记 | 后记 | E | 0 | E0 |
| 分卷重编号 | 第二卷第1章 | C | 51 | C51 |

### 4.3 跨书源对齐算法

基于 SimHash + MinHash + 字数 + 首尾句哈希的多维匹配：

```python
class CrossSourceChapterAligner:
    def align(self, source_a: List[NovelChapter], source_b: List[NovelChapter]) -> AlignmentResult:
        # 双向最优匹配
        # SimHash海明距离 < 3 → 95%+置信度
        # MinHash > 0.85 + 字数差异 < 10% → 中置信度
        # 首句+末句匹配 + 字数差异 < 20% → 低置信度
```

---

## 五、多书源容错策略

### 5.1 健康度评分

```python
class SourceHealthScore:
    def calculate(self, mirror: NovelSourceMirror) -> float:
        score = 100.0
        # 连续失败惩罚（指数衰减）
        score -= min(50, mirror.failure_count ** 2 * 2)
        # 响应时间惩罚
        if mirror.avg_response_ms > 5000:
            score -= min(30, (mirror.avg_response_ms - 5000) / 100)
        # 章节缺失率惩罚
        if mirror.total_chapters_available > 0:
            missing_rate = 1 - (mirror.chapters_fetched / mirror.total_chapters_available)
            score -= missing_rate * 40
        return max(0, min(100, score))
```

### 5.2 自动降级规则

| 条件 | 动作 |
|------|------|
| 连续5章失败 | degraded |
| 连续10章失败 | failed |
| 平均响应 > 10s | 优先级自动降低 |
| 内容一致性 < 50% | content_mismatch，暂停使用 |
| 降级1小时后 | 重新检测，恢复则改回 active |

### 5.3 增量更新策略

- **换源**：创建新镜像，比对缺失章节，只拉取差异，抽样比对 hash
- **新书源更新**：检测目录页章节数变化，只拉取增量章节
- **定时检测**：每天遍历 active 镜像，检测章节数变化

---

## 六、边界处理（5 道质量关卡）

| 关卡 | 检测问题 | 自动处理 |
|------|---------|---------|
| G1-拉取后 | 空章节、防盗、乱码、图片章 | 重解码、切换书源 |
| G2-清洗后 | 段落异常、广告混入、水文、截断 | 去重、过滤、重拉取 |
| G3-解析后 | 标题内容不匹配、时间断层、合并检测 | 指纹比对、标记缺失 |
| G4-指纹后 | 同书源重复、跨canonical相似、哈希碰撞 | 去重、SimHash确认 |
| G5-入库前 | 章节号跳跃、全局字数异常、实体爆发 | 标记缺失、记录统计 |

---

## 七、LLM 自主进化引擎（Hermes + OpenClaw 融合）

### 7.1 五层记忆系统

| 层级 | 载体 | 用途 |
|------|------|------|
| 短期推理内存 | 内存 | 当前解析上下文 |
| 持久化内存 | `app/memory/NOVEL_MEMORY.md` | 书源特征、编码经验 |
| 技能记忆 | `app/skills/novel/**/*.md` | 解析 Skill（agentskills.io） |
| 书籍建模 | `app/memory/books/{id}/BOOK_MODEL.md` | 每本书的写作风格、实体偏好 |
| 全文归档 | SQLite FTS5 | 解析历史、错误记录 |

### 7.2 Skill 系统（agentskills.io 标准）

- **渐进式披露**：Level 0 元数据(~300t) → Level 1 完整说明(~2000t) → Level 2 参考代码(~5000t)
- **自动锻造**：解析成功率 > 80% 时自动生成 SKILL.md
- **自动精炼**：使用 10+ 次后触发优化，A/B 测试新版本
- **跨框架兼容**：遵循 agentskills.io 开放标准

### 7.3 闭环学习回路

```
执行(解析书源) → 评估(成功率/质量) → 抽象(生成Skill) → 精炼(优化代码) → 复用(下次调用)
```

### 7.4 GEP 基因进化协议（OpenClaw 风格）

```python
class GepProtocol:
    async def crystallize(self, patch: CodePatch) -> GepGene:
        # 将成功补丁抽象为通用基因
        # 存储于 app/evolution/assets/gep/genes.json
        
    async def inject(self, error_msg: str, context: dict) -> Optional[str]:
        # 运行时根据错误信息匹配基因
        # 动态注入修复代码
```

### 7.5 代码自进化

- **日志分析器**：扫描解析日志，识别高频错误、性能退化、质量下降
- **代码补丁生成器**：基于错误描述自动生成 Python 修复代码，语法验证后应用
- **自我保护**：备份 → 测试 → 回滚机制，防止进化损坏系统
- **死循环检测**：同一 Skill 短时间内反复修改超过 5 次则暂停

### 7.6 动态注入器

```python
class DynamicInjector:
    async def inject(self, context: ParseContext) -> InjectedContext:
        # 1. 加载匹配 Skill (Level 0 匹配)
        # 2. 加载 GEP 基因 (错误模式匹配)
        # 3. 加载书籍模型 (写作风格)
        # 4. 加载持久化记忆 (书源经验)
        # 5. 组装超级提示词
```

---

## 八、API 端点设计

### 8.1 摄取管理

```
POST   /api/v1/novel/ingest              # 开始摄取
GET    /api/v1/novel/ingest/{job_id}     # 查询进度
GET    /api/v1/novel/books               # 已摄取列表
GET    /api/v1/novel/books/{book_id}     # 书籍详情
DELETE /api/v1/novel/books/{book_id}     # 删除书籍
POST   /api/v1/novel/books/{book_id}/sources  # 添加书源镜像
```

### 8.2 知识查询

```
GET    /api/v1/novel/entities/{book_id}                    # 实体列表
GET    /api/v1/novel/entities/{book_id}/{entity_name}       # 实体详情
GET    /api/v1/novel/timeline/{book_id}                     # 事件时间线
GET    /api/v1/novel/summary/{book_id}                      # 多层摘要
POST   /api/v1/novel/search                                 # 语义搜索
GET    /api/v1/novel/books/{book_id}/align/conflicts        # 章节对齐冲突
POST   /api/v1/novel/chapters/{chapter_id}/resolve          # 人工解决冲突
```

### 8.3 现有 AI 端点增强

| 端点 | 增强方式 |
|------|---------|
| POST /api/v1/llm/character | 加载全书实体+关系图谱，生成人物关系网络 |
| POST /api/v1/llm/world | 提取世界观设定(势力/地理/修炼体系) |
| POST /api/v1/llm/storyline | 从事件表+状态变迁表构建完整时间线 |
| POST /api/v1/llm/chat | RAG检索相关片段+实体卡片 |

---

## 九、项目文件结构

```
app/
├── domain/
│   ├── entities/
│   │   ├── novel.py              # NovelBook/Chapter/Entity/Relationship/Event/StateChange
│   │   ├── source.py             # (现有) BookSource/RssSource/Subscription/FilterRule
│   │   ├── user.py               # (现有) User/UserGroup/ApiKey
│   │   ├── translation.py        # (现有) TranslationJob/Chunk/Dictionary
│   │   └── ai_result.py          # (现有) AICharacterResult/AIWorldResult/AIStorylineResult
│   └── repositories/
│       ├── novel_repo.py         # NovelRepository 抽象接口
│       ├── source_repo.py        # (现有)
│       └── ...
│
├── application/
│   └── services/
│       ├── novel_service.py      # NovelAppService
│       └── ...
│
├── infrastructure/
│   └── persistence/
│       └── sqlite/
│           └── novel_repo_impl.py
│
├── services/
│   ├── novel_understanding/      # 核心引擎目录
│   │   ├── __init__.py
│   │   ├── ingester.py           # 摄取流水线(章节分割+摘要+实体提取)
│   │   ├── multi_source.py       # 多书源管理+健康度评分
│   │   ├── chapter_mapper.py     # 章节标准化映射+跨书源对齐
│   │   ├── entity_extractor.py   # 实体识别与关系抽取
│   │   ├── state_tracker.py      # 角色状态变迁追踪
│   │   ├── summarizer.py         # 分层摘要生成器
│   │   ├── retriever.py          # RAG检索器(BM25+向量+图谱)
│   │   ├── bm25_index.py         # BM25倒排索引(jieba分词)
│   │   ├── embedding.py          # Embedding适配器
│   │   ├── prompt_builder.py     # 富上下文prompt构建器
│   │   └── quality_gates.py      # 5道质量关卡
│   ├── fetcher.py                # (现有) CrawlerPool/SourceFetcher
│   ├── generator.py              # (现有) 写源引擎
│   ├── book_searcher.py          # (现有) 书源搜索
│   └── translator.py             # (现有) 翻译引擎
│
├── evolution/                    # 自主进化引擎
│   ├── __init__.py
│   ├── skill_forge.py            # Skill锻造(Hermes抽象阶段)
│   ├── skill_loader.py           # Skill渐进式加载
│   ├── skill_refiner.py          # Skill精炼+A/B测试
│   ├── code_patcher.py           # 代码补丁生成(OpenClaw自我修复)
│   ├── gep_protocol.py           # GEP基因进化协议
│   ├── dynamic_injector.py       # 动态注入器
│   ├── log_analyzer.py           # 日志分析器
│   ├── parse_evaluator.py        # 解析质量评估
│   ├── reflection_engine.py      # 反思引擎
│   ├── prompt_optimizer.py       # Prompt A/B优化
│   ├── correction_engine.py      # 修正规则应用
│   └── self_protection.py        # 自我保护(备份/回滚/测试)
│
├── memory/                       # 五层记忆系统
│   ├── __init__.py
│   ├── persistent/
│   │   └── NOVEL_MEMORY.md       # 书源特征记忆
│   ├── skills/                   # 技能记忆目录
│   │   └── novel/                # 小说解析Skill库
│   │       ├── parse_html/
│   │       ├── extract_entities/
│   │       ├── split_chapters/
│   │       └── resolve_encoding/
│   ├── book_models/              # 书籍建模
│   │   └── {book_id}/
│   │       └── BOOK_MODEL.md
│   └── archive.py                # SQLite FTS5归档接口
│
├── interfaces/
│   └── api/
│       ├── v1/
│       │   ├── novel.py          # 新增 Novel API
│       │   ├── ai.py             # (现有) 增强后AI端点
│       │   └── ...
│       └── dependencies.py
│
└── core/
    └── ...
```

---

## 十、实施顺序建议

按依赖关系分 5 个阶段实施：

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| Phase 1 | 领域实体 + 数据库Schema + 仓储接口/实现 | P0 |
| Phase 2 | 多书源摄取 + 章节标准化 + 质量关卡 | P0 |
| Phase 3 | 实体提取 + 关系抽取 + 分层摘要 | P0 |
| Phase 4 | RAG检索 + Prompt构建 + 现有AI端点增强 | P1 |
| Phase 5 | Skill系统 + GEP协议 + 代码自进化 | P1 |
