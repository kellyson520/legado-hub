"""
基础设施层 (Infrastructure Layer)

提供技术实现：
- persistence: 持久化（SQLite / PostgreSQL 等）
- cache: 缓存（内存 / Redis）
- ocr: OCR 文字识别（多后端）
- crawler: HTTP 爬虫（UA 轮换、重试、代理）

领域层只依赖接口，不依赖具体实现。
"""

from .ocr import OCREngine, OCRResult, OCRLine
from .crawler import CrawlerEngine, CrawlResult, USER_AGENTS

__all__ = [
    'OCREngine', 'OCRResult', 'OCRLine',
    'CrawlerEngine', 'CrawlResult', 'USER_AGENTS',
]
