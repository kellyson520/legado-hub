"""
技能模块包

10 大技能：
- source: 书源技能（查找、爬虫、编写、管理）⭐ 核心
- collector: 采集技能（小说章节采集）
- extractor: 抽取技能（实体、关系提取）
- auditor: 审计技能（质量检查、冲突检测）
- grapher: 图谱技能（关系图谱生成）
- qa: 问答技能（情节问答、人物查询）
- summarizer: 总结技能（章节摘要、剧情概要）
- writer: 写作技能（内容生成、续写）
- reasoner: 推理技能（关系推理、别名验证）
- ocr: OCR 技能（漫画/图片文字识别）
"""

from .source import SourceSkill
from .collector import CollectorSkill
from .extractor import ExtractorSkill
from .auditor import AuditorSkill
from .grapher import GrapherSkill
from .qa import QASkill
from .summarizer import SummarizerSkill
from .writer import WriterSkill
from .reasoner import ReasonerSkill
from .ocr import OCRSkill

__all__ = [
    'SourceSkill',
    'CollectorSkill',
    'ExtractorSkill',
    'AuditorSkill',
    'GrapherSkill',
    'QASkill',
    'SummarizerSkill',
    'WriterSkill',
    'ReasonerSkill',
    'OCRSkill',
]
