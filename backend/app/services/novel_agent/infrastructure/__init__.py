"""
novel_agent infrastructure 包

向后兼容层：
- OCR / Crawler 统一使用 app.infrastructure 下的实现
- SourceEngine 暂时保留在本地（后续整合到主项目 repository 体系）
- 保持 novel_agent.infrastructure 命名空间的导入兼容性

新代码请直接使用 app.infrastructure.*
"""

from app.infrastructure.ocr import OCREngine, OCRResult, OCRLine
from app.infrastructure.crawler import CrawlerEngine, CrawlResult

# 兼容：旧代码用 ocr_engine() / crawler_engine() 函数获取单例
def ocr_engine(backend: str = "paddleocr", **kwargs) -> OCREngine:
    return OCREngine(backend=backend, **kwargs)

def crawler_engine(**kwargs) -> CrawlerEngine:
    return CrawlerEngine(**kwargs)

# 书源引擎暂时保留本地实现
from .source.source_engine import BookSource, SourceEngine, source_engine

__all__ = [
    'OCREngine', 'OCRResult', 'OCRLine', 'ocr_engine',
    'CrawlerEngine', 'CrawlResult', 'crawler_engine',
    'BookSource', 'SourceEngine', 'source_engine',
]
