# Phase 2: 多源摄入 + 章节标准化 + 五道质量门

> **For agentic workers:** Use executing-plans or inline execution. Steps use checkbox syntax.

**Goal:** 构建章节标题解析、标准化映射、跨书源对齐、健康评分、五道质量门，形成可编排的摄入流水线。

**Architecture:** 纯函数解析器 + 对齐器 + 门控流水线。无外部依赖（正则+内置库），应用层服务编排。

**Tech Stack:** Python 3.11, re, dataclasses, pytest-asyncio

---

## 文件结构

```
app/
├── domain/services/          # 领域服务（纯逻辑，无外部依赖）
│   ├── chapter_parser.py     # 章节标题解析器
│   ├── chapter_mapper.py     # 标准化映射器
│   └── quality_gates.py      # 五道质量门
├── application/services/     # 应用层编排
│   └── novel_ingestion_service.py  # 摄入服务
└── domain/value_objects.py   # 值对象（ParseResult, AlignmentResult等）
tests/
├── test_chapter_parser.py
├── test_chapter_mapper.py
├── test_quality_gates.py
└── test_novel_ingestion_service.py
```

---

### Task 1: Value Objects（值对象）

**Files:**
- Create: `app/domain/value_objects.py`
- Test: `tests/test_value_objects.py`

值对象（不可变、无ID）：
- `ParsedChapterTitle`: core_title, raw_num_str, num, volume, chapter_type
- `CanonicalChapterKey`: type, num, full_key
- `ChapterMatchResult`: confidence, method, source_ch, target_ch
- `QualityGateResult`: gate_name, passed, issues, suggestions

```python
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class ChapterType(str, Enum):
    MAIN = "C"
    PROLOGUE = "P"
    EXTRA = "X"
    EPILOGUE = "E"


@dataclass(frozen=True)
class ParsedChapterTitle:
    raw_title: str
    core_title: str
    raw_num_str: str
    num: int
    volume: str
    chapter_type: ChapterType
    is_valid: bool


@dataclass(frozen=True)
class CanonicalChapterKey:
    chapter_type: ChapterType
    num: int
    full_key: str


@dataclass(frozen=True)
class ChapterMatchResult:
    source_chapter_num: int
    target_chapter_num: int
    confidence: float
    method: str


@dataclass(frozen=True)
class QualityGateResult:
    gate_name: str
    passed: bool
    issues: List[str]
    suggestions: List[str]
```

---

### Task 2: ChapterTitleParser

**Files:**
- Create: `app/domain/services/chapter_parser.py`
- Test: `tests/test_chapter_parser.py`

支持：阿拉伯数字、中文数字、分卷、楔子/番外/后记。

```python
import re
from typing import Optional
from ..value_objects import ParsedChapterTitle, ChapterType


class ChapterTitleParser:
    PATTERNS = {
        'arabic': re.compile(r'(?:第|Chapter\s+|Ch\.?\s*)(\d+)(?:章|:\s*|[-\s])?\s*'),
        'chinese': re.compile(r'第([零一二三四五六七八九十百千万亿\d]+)章\s*'),
        'split': re.compile(r'(?:第)(\d+)(?:章)[（(]?(上|中|下|之一|之二|1|2|3)?[）)]?\s*'),
        'volume_chapter': re.compile(r'(?:第([一二三四五六七八九十\d]+)卷|卷([一二三四五六七八九十\d]+))\s*[·\s]?\s*(?:第(\d+)章|Chapter\s+(\d+))'),
        'prologue': re.compile(r'^(楔子|前言|引子|序章|序幕|开篇|写在前面)'),
        'epilogue': re.compile(r'^(后记|尾声|大结局|终章|完结篇|结束语)'),
        'extra': re.compile(r'^(番外|外传|特别篇|附录|小剧场|if线|平行世界)'),
        'pure_arabic': re.compile(r'^(\d+)\s*[\.、:\-]?\s*(.*)'),
    }

    CHINESE_NUM = {
        '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '百': 100, '千': 1000, '万': 10000, '亿': 100000000,
    }

    @classmethod
    def parse(cls, raw_title: str) -> ParsedChapterTitle:
        ...

    @classmethod
    def chinese_to_int(cls, s: str) -> int:
        ...
```

测试覆盖：
- 第1章 → C1
- 第一百章 → C100
- 楔子 → P0
- 番外一 → X1
- 后记 → E0
- 第二卷第1章 → C(卷基数+1)
- 第1章（上）→ C1
- 纯数字标题 123 → C123
- 无法解析 → is_valid=False

---

### Task 3: ChapterCanonicalMapper

**Files:**
- Create: `app/domain/services/chapter_mapper.py`
- Test: `tests/test_chapter_mapper.py`

```python
from typing import List, Dict
from ..entities.novel import NovelChapter
from ..value_objects import ParsedChapterTitle, CanonicalChapterKey, ChapterType
from .chapter_parser import ChapterTitleParser


class ChapterCanonicalMapper:
    """将原始章节标题映射到标准化 canonical 编号"""

    VOLUME_BASE = {
        1: 0, 2: 50, 3: 100, 4: 150, 5: 200,
        6: 300, 7: 400, 8: 500, 9: 600, 10: 700,
    }

    @classmethod
    def map_single(cls, raw_title: str, book_id: int = 0) -> NovelChapter:
        parsed = ChapterTitleParser.parse(raw_title)
        canonical_type = parsed.chapter_type.value
        canonical_num = cls._calculate_canonical_num(parsed)
        canonical_full = f"{canonical_type}{canonical_num}"
        return NovelChapter(
            book_id=book_id,
            canonical_type=canonical_type,
            canonical_num=canonical_num,
            canonical_full=canonical_full,
            raw_title=raw_title,
            parsed_title_core=parsed.core_title,
            raw_chapter_num=parsed.raw_num_str,
            source_volume=parsed.volume,
            chapter_num=parsed.num,
            chapter_title=parsed.core_title,
        )

    @classmethod
    def map_batch(cls, raw_titles: List[str], book_id: int = 0) -> List[NovelChapter]:
        chapters = []
        for title in raw_titles:
            ch = cls.map_single(title, book_id)
            chapters.append(ch)
        # 检测合并章：连续同编号但字数差异大
        chapters = cls._detect_merged_chapters(chapters)
        return chapters

    @classmethod
    def _calculate_canonical_num(cls, parsed: ParsedChapterTitle) -> int:
        if parsed.chapter_type == ChapterType.MAIN and parsed.volume:
            base = cls._volume_to_base(parsed.volume)
            return base + parsed.num
        return parsed.num

    @classmethod
    def _volume_to_base(cls, volume_str: str) -> int:
        try:
            vol = int(volume_str)
        except ValueError:
            vol = ChapterTitleParser.chinese_to_int(volume_str) or 1
        return cls.VOLUME_BASE.get(vol, (vol - 1) * 100)

    @classmethod
    def _detect_merged_chapters(cls, chapters: List[NovelChapter]) -> List[NovelChapter]:
        ...
```

---

### Task 4: CrossSourceChapterAligner

**Files:**
- Create: `app/domain/services/chapter_aligner.py`
- Test: `tests/test_chapter_aligner.py`

```python
from typing import List, Tuple
from dataclasses import dataclass
from ..entities.novel import NovelChapter


@dataclass
class AlignmentResult:
    matches: List[Tuple[int, int, float]]  # (source_idx, target_idx, confidence)
    unmatched_source: List[int]
    unmatched_target: List[int]


class CrossSourceChapterAligner:
    """跨书源章节对齐，基于标题+字数+序号"""

    @classmethod
    def align(
        cls,
        source_chapters: List[NovelChapter],
        target_chapters: List[NovelChapter],
    ) -> AlignmentResult:
        matches = []
        matched_target = set()

        for si, sch in enumerate(source_chapters):
            best_ti = -1
            best_conf = 0.0
            for ti, tch in enumerate(target_chapters):
                if ti in matched_target:
                    continue
                conf = cls._match_confidence(sch, tch)
                if conf > best_conf and conf >= 0.5:
                    best_conf = conf
                    best_ti = ti
            if best_ti >= 0:
                matches.append((si, best_ti, best_conf))
                matched_target.add(best_ti)

        unmatched_source = [i for i in range(len(source_chapters)) if i not in [m[0] for m in matches]]
        unmatched_target = [i for i in range(len(target_chapters)) if i not in matched_target]
        return AlignmentResult(matches, unmatched_source, unmatched_target)

    @classmethod
    def _match_confidence(cls, a: NovelChapter, b: NovelChapter) -> float:
        # canonical_full 完全匹配 → 1.0
        if a.canonical_full and a.canonical_full == b.canonical_full:
            return 1.0
        # core_title 相似 → 0.9
        if a.parsed_title_core and a.parsed_title_core == b.parsed_title_core:
            return 0.9
        # 字数接近 + 序号接近 → 0.7
        if a.word_count > 0 and b.word_count > 0:
            word_diff_ratio = abs(a.word_count - b.word_count) / max(a.word_count, b.word_count)
            if word_diff_ratio < 0.1:
                num_diff = abs(a.chapter_num - b.chapter_num)
                if num_diff <= 1:
                    return 0.7
        return 0.0
```

---

### Task 5: SourceHealthScore

**Files:**
- Create: `app/domain/services/source_health.py`
- Test: `tests/test_source_health.py`

```python
from ..entities.novel import NovelSourceMirror


class SourceHealthScore:
    @classmethod
    def calculate(cls, mirror: NovelSourceMirror) -> float:
        score = 100.0
        score -= min(50, mirror.failure_count ** 2 * 2)
        if mirror.avg_response_ms > 5000:
            score -= min(30, (mirror.avg_response_ms - 5000) / 100)
        if mirror.total_chapters_available > 0:
            missing_rate = 1 - (mirror.chapters_fetched / mirror.total_chapters_available)
            score -= missing_rate * 40
        return max(0.0, min(100.0, score))

    @classmethod
    def determine_status(cls, mirror: NovelSourceMirror) -> str:
        score = cls.calculate(mirror)
        if mirror.failure_count >= 10 or score < 20:
            return "failed"
        if mirror.failure_count >= 5 or score < 50:
            return "degraded"
        return "active"
```

---

### Task 6: 五道质量门 (QualityGates)

**Files:**
- Create: `app/domain/services/quality_gates.py`
- Test: `tests/test_quality_gates.py`

```python
from typing import List, Callable
from ..value_objects import QualityGateResult
from ..entities.novel import NovelChapter


class QualityGates:
    """五道质量门流水线"""

    @classmethod
    def run_all(cls, chapter: NovelChapter, raw_text: str = "") -> List[QualityGateResult]:
        return [
            cls.g1_fetch_gate(raw_text),
            cls.g2_clean_gate(raw_text),
            cls.g3_parse_gate(chapter, raw_text),
            cls.g4_fingerprint_gate(chapter),
            cls.g5_global_gate(chapter),
        ]

    @classmethod
    def g1_fetch_gate(cls, raw_text: str) -> QualityGateResult:
        issues = []
        suggestions = []
        if len(raw_text) < 100:
            issues.append("章节内容过短，可能为空章节或防盗章")
            suggestions.append("尝试切换书源重拉")
        if "img" in raw_text.lower() or "<image" in raw_text.lower():
            issues.append("检测到图片章节")
        # 乱码检测：大量重复替换符
        if raw_text.count("�") > 5:
            issues.append("检测到编码错误（乱码）")
            suggestions.append("尝试 UTF-8/GBK 重新解码")
        return QualityGateResult("G1-Fetch", len(issues) == 0, issues, suggestions)

    @classmethod
    def g2_clean_gate(cls, raw_text: str) -> QualityGateResult:
        issues = []
        # 广告检测
        ad_keywords = ["加入书签", "投推荐票", "下一章", "天才壹秒記住", "手机阅读"]
        for kw in ad_keywords:
            if kw in raw_text:
                issues.append(f"检测到广告关键词: {kw}")
        # 水文检测：大量重复段落
        paragraphs = [p for p in raw_text.split("\n") if p.strip()]
        if len(paragraphs) > 5:
            unique_ratio = len(set(paragraphs)) / len(paragraphs)
            if unique_ratio < 0.7:
                issues.append("段落重复率过高，疑似水文")
        return QualityGateResult("G2-Clean", len(issues) == 0, issues, [])

    @classmethod
    def g3_parse_gate(cls, chapter: NovelChapter, raw_text: str) -> QualityGateResult:
        issues = []
        if chapter.chapter_title and chapter.chapter_title not in raw_text[:200]:
            issues.append("标题未出现在正文前200字中")
        return QualityGateResult("G3-Parse", len(issues) == 0, issues, [])

    @classmethod
    def g4_fingerprint_gate(cls, chapter: NovelChapter) -> QualityGateResult:
        issues = []
        if chapter.word_count > 0 and chapter.word_count < 500:
            issues.append("章节字数过少（<500），可能为截断")
        return QualityGateResult("G4-Fingerprint", len(issues) == 0, issues, [])

    @classmethod
    def g5_global_gate(cls, chapter: NovelChapter) -> QualityGateResult:
        issues = []
        if chapter.canonical_num <= 0 and chapter.canonical_type == "C":
            issues.append("正文章节编号异常")
        return QualityGateResult("G5-Global", len(issues) == 0, issues, [])
```

---

### Task 7: NovelIngestionService（应用层编排）

**Files:**
- Create: `app/application/services/novel_ingestion_service.py`
- Test: `tests/test_novel_ingestion_service.py`

```python
from typing import List
from app.domain.repositories.novel_repo import NovelRepository
from app.domain.services.chapter_mapper import ChapterCanonicalMapper
from app.domain.services.quality_gates import QualityGates
from app.domain.entities.novel import NovelBook, NovelStatus


class NovelIngestionService:
    def __init__(self, repo: NovelRepository):
        self._repo = repo

    async def ingest_catalog(self, book_url: str, book_name: str, raw_titles: List[str]) -> NovelBook:
        book = NovelBook(book_url=book_url, book_name=book_name)
        book = await self._repo.save_book(book)
        book.status = NovelStatus.INGESTING
        await self._repo.update_book_status(book.id, NovelStatus.INGESTING)

        chapters = ChapterCanonicalMapper.map_batch(raw_titles, book_id=book.id)
        for ch in chapters:
            await self._repo.save_chapter(ch)

        book.status = NovelStatus.SUMMARIZING
        book.total_chapters = len(chapters)
        await self._repo.update_book_status(book.id, NovelStatus.SUMMARIZING, progress=0.3)
        return book
```

---

### Task 8: 全回归测试

Run: `cd /workspace/legado-hub/backend && python -m pytest --tb=short -q`
Expected: 571+ tests all pass
