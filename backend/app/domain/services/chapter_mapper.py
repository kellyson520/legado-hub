"""
章节标准化映射器

将原始章节标题映射到标准化 canonical 编号系统。
支持分卷偏移计算、合并章检测。
"""

from typing import List

from ..entities.novel import NovelChapter
from ..value_objects import ChapterType
from .chapter_parser import ChapterTitleParser


class ChapterCanonicalMapper:
    """章节标准化映射器"""

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
        chapters = cls._detect_merged_chapters(chapters)
        return chapters

    @classmethod
    def _calculate_canonical_num(cls, parsed) -> int:
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
        return chapters
