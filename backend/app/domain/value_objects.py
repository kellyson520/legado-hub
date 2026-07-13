"""
NovelUnderstanding 值对象

值对象特点：
- 不可变（frozen dataclass）
- 无唯一标识
- 通过属性值判断相等
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum


class ChapterType(str, Enum):
    """章节类型"""
    MAIN = "C"
    PROLOGUE = "P"
    EXTRA = "X"
    EPILOGUE = "E"


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
