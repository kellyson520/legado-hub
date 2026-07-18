"""Compatibility facade for the legacy source-fetcher import path.

The implementation lives in ``app.infrastructure.crawler``.  New code must
depend on that infrastructure module or on an application port instead.
"""

from app.infrastructure.crawler.source_fetcher import CrawlerPool, SourceChecker, SourceFetcher

__all__ = ["CrawlerPool", "SourceChecker", "SourceFetcher"]
