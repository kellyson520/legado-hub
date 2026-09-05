"""
领域实体 - 翻译模块的核心领域对象

实体特点：
- 有唯一标识（job_id / chunk_index）
- 包含业务规则和行为方法
- 不依赖任何基础设施（无 SQLAlchemy、无 HTTP 等）
- 纯 Python 对象，可在任何环境中运行
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class TranslationStatus(str, Enum):
    """翻译任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # 部分完成（有缓存命中，也有失败）


class TranslationProvider(str, Enum):
    """翻译服务提供商"""
    GOOGLE = "google"
    LLM = "llm"


@dataclass
class TextChunk:
    """文本分块 - 翻译的最小单元"""
    index: int
    content: str
    paragraph_indices: List[int] = field(default_factory=list)

    @property
    def length(self) -> int:
        return len(self.content)


@dataclass
class TranslationChunk:
    """已翻译的块"""
    index: int
    original: str
    translated: str = ""
    status: TranslationStatus = TranslationStatus.PENDING
    error_msg: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def mark_translated(self, translated_text: str):
        self.translated = translated_text
        self.status = TranslationStatus.COMPLETED
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error_msg: str):
        self.status = TranslationStatus.FAILED
        self.error_msg = error_msg
        self.updated_at = datetime.utcnow()


@dataclass
class TranslationDictionary:
    """翻译词典 - 专有名词映射表"""
    id: int = 0
    book_url: str = ""
    book_name: str = ""
    entries: Dict[str, str] = field(default_factory=dict)
    max_entries: int = 80
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_entry(self, original: str, translated: str) -> bool:
        """添加词典条目，超过上限时返回 False"""
        if len(self.entries) >= self.max_entries and original not in self.entries:
            return False
        self.entries[original] = translated
        self.updated_at = datetime.utcnow()
        return True

    def merge_entries(self, new_entries: Dict[str, str]) -> int:
        """合并新条目，返回实际添加的数量"""
        added = 0
        for original, translated in new_entries.items():
            if self.add_entry(original, translated):
                added += 1
        return added

    def to_prompt_text(self) -> str:
        """转换为 LLM 提示词中的词典文本"""
        lines = []
        for original, translated in self.entries.items():
            lines.append(f"{original} -> {translated}")
        return "\n".join(lines)


@dataclass
class TranslationJob:
    """翻译任务 - 章节的完整翻译作业"""
    id: int = 0
    job_id: str = ""  # 业务唯一标识（如 book_url + chapter_id 的哈希）
    book_url: str = ""
    book_name: str = ""
    chapter_id: str = ""
    chapter_title: str = ""
    original_text: str = ""
    translated_text: str = ""
    provider: TranslationProvider = TranslationProvider.LLM
    target_language: str = "zh-CN"
    status: TranslationStatus = TranslationStatus.PENDING
    total_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0
    error_msg: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def progress(self) -> float:
        """计算翻译进度百分比"""
        if self.total_chunks <= 0:
            return 0.0
        return round(self.completed_chunks / self.total_chunks * 100, 2)

    @property
    def is_done(self) -> bool:
        """是否已完成（成功或失败）"""
        return self.status in (TranslationStatus.COMPLETED, TranslationStatus.FAILED)

    def mark_started(self):
        self.status = TranslationStatus.RUNNING
        self.updated_at = datetime.utcnow()

    def mark_completed(self, translated_text: str):
        self.translated_text = translated_text
        self.status = TranslationStatus.COMPLETED
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error_msg: str):
        self.status = TranslationStatus.FAILED
        self.error_msg = error_msg
        self.updated_at = datetime.utcnow()

    def update_progress(self, completed: int, failed: int = 0):
        self.completed_chunks = completed
        self.failed_chunks = failed
        self.updated_at = datetime.utcnow()
        if self.completed_chunks + self.failed_chunks >= self.total_chunks:
            if self.failed_chunks > 0 and self.completed_chunks > 0:
                self.status = TranslationStatus.PARTIAL
            elif self.failed_chunks > 0:
                self.status = TranslationStatus.FAILED
            else:
                self.status = TranslationStatus.COMPLETED
