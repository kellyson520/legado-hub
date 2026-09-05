"""
章节标题解析器

支持：阿拉伯数字、中文数字、分卷、楔子/番外/后记/尾声等
"""

import re
from typing import Optional

from ..value_objects import ParsedChapterTitle, ChapterType


class ChapterTitleParser:
    """章节标题解析器"""

    PATTERNS = {
        'arabic': re.compile(r'(?:第|Chapter\s+|Ch\.?\s*)(\d+)(?:章|:\s*|[-\s])?\s*'),
        'chinese': re.compile(r'第([零一二三四五六七八九十百千万亿\d]+)章\s*'),
        'split': re.compile(r'(?:第)(\d+)(?:章)[（(]?(上|中|下|之一|之二|1|2|3)?[）)]?\s*'),
        'volume_chapter': re.compile(
            r'(?:第([一二三四五六七八九十\d]+)卷|卷([一二三四五六七八九十\d]+))\s*[·\s]?\s*(?:第(\d+)章|Chapter\s+(\d+))'
        ),
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
        if not raw_title or not raw_title.strip():
            return cls._invalid(raw_title)

        title = raw_title.strip()

        # 1. 检查特殊章节类型
        for ptype in ['prologue', 'epilogue', 'extra']:
            m = cls.PATTERNS[ptype].match(title)
            if m:
                return cls._special_type(title, ptype, m.group(1))

        # 2. 检查分卷格式
        m = cls.PATTERNS['volume_chapter'].match(title)
        if m:
            return cls._volume_match(title, m)

        # 3. 检查分上下章（在纯阿拉伯数字之前，避免第100章（上）被阿拉伯匹配）
        m = cls.PATTERNS['split'].match(title)
        if m:
            return cls._split_match(title, m)

        # 4. 检查第X章（阿拉伯数字）
        m = cls.PATTERNS['arabic'].match(title)
        if m:
            return cls._arabic_match(title, m)

        # 5. 检查第X章（中文数字）
        m = cls.PATTERNS['chinese'].match(title)
        if m:
            return cls._chinese_match(title, m)

        # 6. 纯数字开头
        m = cls.PATTERNS['pure_arabic'].match(title)
        if m:
            return cls._pure_arabic_match(title, m)

        return cls._invalid(title)

    @classmethod
    def chinese_to_int(cls, s: str) -> int:
        """中文数字转整数，支持：十、十一、一百二十三、一千零五"""
        if not s:
            return 0
        # 先尝试直接转数字
        try:
            return int(s)
        except ValueError:
            pass

        total = 0
        current = 0
        for ch in s:
            if ch in cls.CHINESE_NUM:
                num = cls.CHINESE_NUM[ch]
                if num >= 10:
                    if current == 0:
                        current = 1
                    total += current * num
                    current = 0
                else:
                    current = current * 10 + num if current > 0 else num
        total += current
        return total

    @classmethod
    def _invalid(cls, title: str) -> ParsedChapterTitle:
        return ParsedChapterTitle(
            raw_title=title, core_title=title, raw_num_str="",
            num=0, volume="", chapter_type=ChapterType.MAIN, is_valid=False
        )

    @classmethod
    def _special_type(cls, title: str, ptype: str, keyword: str) -> ParsedChapterTitle:
        type_map = {
            'prologue': ChapterType.PROLOGUE,
            'epilogue': ChapterType.EPILOGUE,
            'extra': ChapterType.EXTRA,
        }
        # 尝试从标题中提取数字（如"番外一"）
        num = 0
        m = re.search(r'(\d+)', title)
        if m:
            num = int(m.group(1))
        else:
            # 尝试中文数字
            m = re.search(r'[零一二三四五六七八九十百千万亿]+', title)
            if m:
                num = cls.chinese_to_int(m.group())

        return ParsedChapterTitle(
            raw_title=title, core_title=keyword, raw_num_str=str(num) if num else "",
            num=num, volume="", chapter_type=type_map[ptype], is_valid=True
        )

    @classmethod
    def _volume_match(cls, title: str, m: re.Match) -> ParsedChapterTitle:
        volume_str = m.group(1) or m.group(2) or ""
        chapter_num_str = m.group(3) or m.group(4) or "0"
        chapter_num = int(chapter_num_str)
        core = title[m.end():].strip() if m.end() < len(title) else ""
        return ParsedChapterTitle(
            raw_title=title, core_title=core or title,
            raw_num_str=chapter_num_str, num=chapter_num,
            volume=volume_str, chapter_type=ChapterType.MAIN, is_valid=True
        )

    @classmethod
    def _arabic_match(cls, title: str, m: re.Match) -> ParsedChapterTitle:
        num = int(m.group(1))
        core = title[m.end():].strip()
        return ParsedChapterTitle(
            raw_title=title, core_title=core or title,
            raw_num_str=str(num), num=num,
            volume="", chapter_type=ChapterType.MAIN, is_valid=True
        )

    @classmethod
    def _chinese_match(cls, title: str, m: re.Match) -> ParsedChapterTitle:
        num_str = m.group(1)
        num = cls.chinese_to_int(num_str)
        core = title[m.end():].strip()
        return ParsedChapterTitle(
            raw_title=title, core_title=core or title,
            raw_num_str=num_str, num=num,
            volume="", chapter_type=ChapterType.MAIN, is_valid=True
        )

    @classmethod
    def _split_match(cls, title: str, m: re.Match) -> ParsedChapterTitle:
        num = int(m.group(1))
        part = m.group(2) or ""
        core = title[m.end():].strip()
        return ParsedChapterTitle(
            raw_title=title, core_title=core or title,
            raw_num_str=f"{num}-{part}", num=num,
            volume="", chapter_type=ChapterType.MAIN, is_valid=True
        )

    @classmethod
    def _pure_arabic_match(cls, title: str, m: re.Match) -> ParsedChapterTitle:
        num = int(m.group(1))
        core = m.group(2).strip() if m.group(2) else ""
        return ParsedChapterTitle(
            raw_title=title, core_title=core or title,
            raw_num_str=str(num), num=num,
            volume="", chapter_type=ChapterType.MAIN, is_valid=True
        )
