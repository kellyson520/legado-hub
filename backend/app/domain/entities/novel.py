"""
NovelUnderstanding 自主进化引擎 - 领域实体

包含：
- 6 个枚举类（状态、实体类型、关系类型、事件类型、状态字段、摄入来源）
- 13 个 dataclass 实体（小说、章节、实体、关系、事件、状态变更、镜像、进化相关）

纯业务对象，不依赖任何基础设施。
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional


# ========== 枚举类 ==========

class NovelStatus(str, Enum):
    """小说处理状态"""
    PENDING = "pending"
    INGESTING = "ingesting"
    SUMMARIZING = "summarizing"
    EXTRACTING = "extracting"
    READY = "ready"
    ERROR = "error"


class EntityType(str, Enum):
    """实体类型"""
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
    FACTION = "faction"
    REALM = "realm"
    CONCEPT = "concept"


class RelationType(str, Enum):
    """关系类型"""
    ALLY = "ally"
    ENEMY = "enemy"
    MASTER = "master"
    SUBORDINATE = "subordinate"
    LOVER = "lover"
    FAMILY = "family"
    RIVAL = "rival"
    CUSTOM = "custom"


class EventType(str, Enum):
    """事件类型"""
    BATTLE = "battle"
    BREAKTHROUGH = "breakthrough"
    BETRAYAL = "betrayal"
    REUNION = "reunion"
    DISCOVERY = "discovery"
    DEPARTURE = "departure"
    DEATH = "death"
    CUSTOM = "custom"


class StateField(str, Enum):
    """状态字段类型"""
    REALM = "realm"
    ABILITY = "ability"
    STATUS = "status"
    RELATIONSHIP = "relationship"
    POSSESSION = "possession"
    POSITION = "position"
    EMOTION = "emotion"
    CUSTOM = "custom"


class IngestSource(str, Enum):
    """内容摄入来源"""
    BOOK_SOURCE = "book_source"
    UPLOAD = "upload"


# ========== 核心实体 ==========

@dataclass
class NovelBook:
    """小说索引实体"""
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
    owner_scope: str = "legacy"


@dataclass
class NovelSourceMirror:
    """书源镜像实体 - 多源容错"""
    id: int = 0
    book_id: int = 0
    source_url: str = ""
    source_name: str = ""
    priority: int = 0
    status: str = "active"  # active / degraded / failed
    last_check_at: Optional[datetime] = None
    last_check_result: str = ""
    avg_response_ms: int = 0
    failure_count: int = 0
    total_chapters_available: int = 0
    chapters_fetched: int = 0
    content_fingerprint: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ChapterFingerprint:
    """章节内容指纹 - 跨源对齐"""
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
    """章节元数据实体"""
    id: int = 0
    book_id: int = 0
    canonical_type: str = "C"  # C=正章, P=序/前言, X=番外, E=后记
    canonical_num: int = 0
    canonical_full: str = ""  # 如 "C1", "P0", "X1"
    raw_title: str = ""  # 原始标题
    parsed_title_core: str = ""  # 解析后的核心标题（去除序号）
    raw_chapter_num: str = ""  # 原始章节号字符串
    source_volume: str = ""  # 原始卷名
    chapter_num: int = 0  # 原始数字序号
    chapter_title: str = ""
    word_count: int = 0
    raw_text_hash: str = ""
    raw_text: str = ""  # 章节正文（可选，小体量书籍可存）
    quality_score: float = 0.0  # 质量分 0-1
    summary: str = ""
    key_events: List[str] = field(default_factory=list)
    character_appearances: Dict[str, int] = field(default_factory=dict)
    location_appearances: Dict[str, int] = field(default_factory=dict)
    mood_tags: List[str] = field(default_factory=list)
    arc_tag: str = ""  # 篇章标签
    arc_summary: str = ""  # 篇章摘要
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NovelChapterMirror:
    """章节镜像实体 - 记录每个源上的章节状态"""
    id: int = 0
    chapter_id: int = 0
    mirror_id: int = 0
    source_url: str = ""
    chapter_num: int = 0
    fetch_status: str = "pending"  # pending / fetched / failed / empty
    word_count: int = 0
    content_hash: str = ""
    fetch_error: Optional[str] = None
    fetched_at: Optional[datetime] = None
    response_time_ms: int = 0


# ========== 知识图谱实体 ==========

@dataclass
class NovelEntity:
    """知识图谱节点 - 人物/地点/物品/势力/境界/概念"""
    id: int = 0
    book_id: int = 0
    name: str = ""
    aliases: List[str] = field(default_factory=list)
    entity_type: EntityType = field(default=EntityType.CHARACTER)
    description: str = ""
    first_appearance_ch: int = 0
    last_appearance_ch: int = 0
    appearance_count: int = 0
    importance_score: int = 3  # 1-5，5为最重要
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NovelRelationship:
    """知识图谱边 - 实体间关系"""
    id: int = 0
    book_id: int = 0
    source_entity: str = ""  # 源实体名称
    target_entity: str = ""  # 目标实体名称
    relation_type: RelationType = field(default=RelationType.CUSTOM)
    description: str = ""
    since_chapter: int = 0
    until_chapter: Optional[int] = None  # None 表示持续到当前
    confidence: float = 0.8
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NovelEvent:
    """事件实体 - 发生在特定章节的重要事件"""
    id: int = 0
    book_id: int = 0
    chapter_id: int = 0
    chapter_num: int = 0
    event_type: EventType = field(default=EventType.CUSTOM)
    description: str = ""
    participants: List[str] = field(default_factory=list)
    location: str = ""
    importance: int = 3  # 1-5
    related_entities: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NovelStateChange:
    """状态变更实体 - 记录实体属性随章节的变化"""
    id: int = 0
    book_id: int = 0
    entity_name: str = ""
    chapter_id: int = 0
    chapter_num: int = 0
    field_name: StateField = field(default=StateField.CUSTOM)
    before_value: str = ""
    after_value: str = ""
    trigger_event: str = ""  # 触发此变更的事件描述
    confidence: float = 0.8
    created_at: datetime = field(default_factory=datetime.utcnow)


# ========== 进化相关实体 ==========

@dataclass
class EvolutionFeedback:
    """用户反馈 / 自我评估反馈"""
    id: int = 0
    book_id: int = 0
    feedback_type: str = ""  # user_correction / self_eval / quality_check
    target_type: str = ""  # entity / relationship / event / summary / rule
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
    """进化规则 - 从反馈中提取的模式替换规则"""
    id: int = 0
    book_id: int = 0  # 0 表示全局规则
    rule_type: str = ""  # extraction / correction / summarization
    pattern: str = ""  # 匹配模式
    replacement: str = ""  # 替换/修正内容
    condition: str = ""  # 应用条件（JSON 字符串）
    hit_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    active: bool = True
    created_from_feedback_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PromptTemplate:
    """Prompt 模板版本管理"""
    id: int = 0
    template_name: str = ""
    version: int = 1
    template_text: str = ""
    success_rate: float = 0.0
    avg_token_usage: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GepGene:
    """GEP 基因 - 代码自修复的基因片段"""
    id: str = ""  # 基因唯一标识（如 gene_001）
    name: str = ""
    trigger_pattern: str = ""  # 触发此基因的错误模式（正则或关键词）
    fix_strategy: str = ""  # 修复策略描述
    code_template: str = ""  # 代码模板（含占位符）
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
