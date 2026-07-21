"""
NovelUnderstanding 值对象

值对象特点：
- 不可变（frozen dataclass）
- 无唯一标识
- 通过属性值判断相等
"""

from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple
from enum import Enum


class ChapterType(str, Enum):
    """章节类型"""
    MAIN = "C"
    PROLOGUE = "P"
    EXTRA = "X"
    EPILOGUE = "E"


@dataclass(frozen=True)
class OwnerScope:
    """Stable authorization/cache identity for persisted novel data."""

    value: str
    kind: Literal["user", "api_key", "legacy"] = "user"

    def __post_init__(self) -> None:
        if not self.value or (self.kind != "legacy" and ":" not in self.value):
            raise ValueError("owner scope must contain a non-empty namespace")
        if self.kind not in ("user", "api_key", "legacy"):
            raise ValueError(f"unsupported owner scope kind: {self.kind}")

    @classmethod
    def user(cls, user_id: int) -> "OwnerScope":
        return cls(f"user:{int(user_id)}", "user")

    @classmethod
    def api_key(cls, api_key_id: int) -> "OwnerScope":
        return cls(f"api-key:{int(api_key_id)}", "api_key")

    @classmethod
    def legacy(cls) -> "OwnerScope":
        return cls("legacy", "legacy")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ParsedChapterTitle:
    """解析后的章节标题"""
    raw_title: str
    core_title: str
    raw_num_str: str
    num: int
    volume: str
    chapter_type: ChapterType
    is_valid: bool


@dataclass(frozen=True)
class CanonicalChapterKey:
    """标准化章节键"""
    chapter_type: ChapterType
    num: int
    full_key: str


@dataclass(frozen=True)
class ChapterMatchResult:
    """跨书源章节匹配结果"""
    source_chapter_num: int
    target_chapter_num: int
    confidence: float
    method: str


@dataclass(frozen=True)
class QualityGateResult:
    """质量门检查结果"""
    gate_name: str
    passed: bool
    issues: List[str]
    suggestions: List[str]


@dataclass(frozen=True)
class AlignmentResult:
    """跨书源对齐结果"""
    matches: List[Tuple[int, int, float]]  # (source_idx, target_idx, confidence)
    unmatched_source: List[int]
    unmatched_target: List[int]
