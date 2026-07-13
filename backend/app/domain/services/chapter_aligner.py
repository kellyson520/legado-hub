"""
跨书源章节对齐器

基于标题、字数、序号进行跨书源章节匹配对齐。
"""

from typing import List

from ..entities.novel import NovelChapter
from ..value_objects import AlignmentResult


class CrossSourceChapterAligner:
    """跨书源章节对齐器"""

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
            max_wc = max(a.word_count, b.word_count)
            word_diff_ratio = abs(a.word_count - b.word_count) / max_wc if max_wc > 0 else 1.0
            if word_diff_ratio < 0.1:
                num_diff = abs(a.chapter_num - b.chapter_num)
                if num_diff <= 1:
                    return 0.7
        return 0.0
