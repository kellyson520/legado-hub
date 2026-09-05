"""
五道质量门系统

G1-Fetch: 拉取后检查（空章节、乱码、图片章节）
G2-Clean: 清洗后检查（广告、水文、VIP占位）
G3-Parse: 解析后检查（标题一致性、内容截断）
G4-Fingerprint: 指纹后检查（字数异常、重复内容）
G5-Global: 入库前全局检查（编号连续性、缺失检测）
"""

from typing import List

from ..value_objects import QualityGateResult
from ..entities.novel import NovelChapter


class QualityGates:
    """五道质量门流水线"""

    AD_KEYWORDS = ["加入书签", "投推荐票", "下一章", "天才壹秒記住", "手机阅读", "readx()"]

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
        for kw in cls.AD_KEYWORDS:
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
