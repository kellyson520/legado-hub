"""
领域实体 - 源管理模块的核心领域对象

实体特点：
- 有唯一标识（bookSourceUrl / sourceUrl）
- 包含业务规则和行为方法
- 不依赖任何基础设施（无 SQLAlchemy、无 HTTP 等）
- 纯 Python 对象，可在任何环境中运行
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class BookSource:
    """书源领域实体"""
    bookSourceUrl: str
    bookSourceName: str
    bookSourceGroup: Optional[str] = None
    bookSourceType: int = 0
    bookUrlPattern: Optional[str] = None
    customOrder: int = 0
    enabled: bool = True
    enabledExplore: bool = True
    jsLib: Optional[str] = None
    enabledCookieJar: bool = True
    concurrentRate: Optional[str] = None
    header: Optional[str] = None
    loginUrl: Optional[str] = None
    loginUi: Optional[str] = None
    loginCheckJs: Optional[str] = None
    coverDecodeJs: Optional[str] = None
    bookSourceComment: Optional[str] = None
    variableComment: Optional[str] = None
    lastUpdateTime: int = 0
    respondTime: int = 180000
    weight: int = 0
    exploreUrl: Optional[str] = None
    exploreScreen: Optional[str] = None
    ruleExplore: Optional[Dict[str, Any]] = None
    searchUrl: Optional[str] = None
    ruleSearch: Optional[Dict[str, Any]] = None
    ruleBookInfo: Optional[Dict[str, Any]] = None
    ruleToc: Optional[Dict[str, Any]] = None
    ruleContent: Optional[Dict[str, Any]] = None
    ruleReview: Optional[Dict[str, Any]] = None
    # Hub 内部字段
    sourceStatus: str = "unknown"  # ok, error, unknown
    lastCheckTime: Optional[datetime] = None
    errorMsg: Optional[str] = None
    sourceOrigin: Optional[str] = None
    createdAt: datetime = field(default_factory=datetime.utcnow)
    updatedAt: datetime = field(default_factory=datetime.utcnow)

    @property
    def id(self) -> str:
        """实体唯一标识"""
        return self.bookSourceUrl

    def is_available(self) -> bool:
        """业务规则：源是否可用"""
        return self.enabled and self.sourceStatus == "ok"

    def mark_checked(self, status: str, error_msg: Optional[str] = None):
        """标记检查状态"""
        self.sourceStatus = status
        self.lastCheckTime = datetime.utcnow()
        self.errorMsg = error_msg
        self.updatedAt = datetime.utcnow()

    def to_legado_dict(self) -> Dict[str, Any]:
        """转换为 Legado 标准格式（移除内部字段）"""
        hub_fields = {"sourceStatus", "lastCheckTime", "errorMsg", "sourceOrigin", "createdAt", "updatedAt"}
        result = {}
        for k, v in self.__dict__.items():
            if k not in hub_fields and v is not None and v != "":
                result[k] = v
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BookSource":
        """从字典创建实体"""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class RssSource:
    """订阅源领域实体"""
    sourceUrl: str
    sourceName: str
    sourceIcon: Optional[str] = None
    sourceGroup: Optional[str] = None
    sourceComment: Optional[str] = None
    enabled: bool = True
    variableComment: Optional[str] = None
    jsLib: Optional[str] = None
    enabledCookieJar: bool = True
    concurrentRate: Optional[str] = None
    header: Optional[str] = None
    loginUrl: Optional[str] = None
    loginUi: Optional[str] = None
    loginCheckJs: Optional[str] = None
    coverDecodeJs: Optional[str] = None
    sortUrl: Optional[str] = None
    singleUrl: bool = False
    articleStyle: int = 0
    ruleArticles: Optional[str] = None
    ruleNextPage: Optional[str] = None
    ruleTitle: Optional[str] = None
    rulePubDate: Optional[str] = None
    ruleDescription: Optional[str] = None
    ruleImage: Optional[str] = None
    ruleLink: Optional[str] = None
    ruleContent: Optional[str] = None
    contentWhitelist: Optional[str] = None
    contentBlacklist: Optional[str] = None
    shouldOverrideUrlLoading: Optional[str] = None
    style: Optional[str] = None
    enableJs: bool = True
    loadWithBaseUrl: bool = True
    injectJs: Optional[str] = None
    preloadJs: Optional[str] = None
    startHtml: Optional[str] = None
    startStyle: Optional[str] = None
    startJs: Optional[str] = None
    showWebLog: bool = False
    lastUpdateTime: int = 0
    customOrder: int = 0
    type: int = 0
    preload: bool = False
    cacheFirst: bool = False
    searchUrl: Optional[str] = None
    redirectPolicy: str = "ASK_CROSS_ORIGIN"
    # Hub 内部字段
    sourceStatus: str = "unknown"
    lastCheckTime: Optional[datetime] = None
    errorMsg: Optional[str] = None
    sourceOrigin: Optional[str] = None
    createdAt: datetime = field(default_factory=datetime.utcnow)
    updatedAt: datetime = field(default_factory=datetime.utcnow)

    @property
    def id(self) -> str:
        return self.sourceUrl

    def is_available(self) -> bool:
        return self.enabled and self.sourceStatus == "ok"

    def mark_checked(self, status: str, error_msg: Optional[str] = None):
        self.sourceStatus = status
        self.lastCheckTime = datetime.utcnow()
        self.errorMsg = error_msg
        self.updatedAt = datetime.utcnow()

    def to_legado_dict(self) -> Dict[str, Any]:
        hub_fields = {"sourceStatus", "lastCheckTime", "errorMsg", "sourceOrigin", "createdAt", "updatedAt"}
        result = {}
        for k, v in self.__dict__.items():
            if k not in hub_fields and v is not None and v != "":
                result[k] = v
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RssSource":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class Subscription:
    """订阅领域实体"""
    id: int = 0
    name: str = ""
    url: str = ""
    subType: str = "book"  # book, rss, mixed
    enabled: bool = True
    autoFetch: bool = True
    fetchInterval: int = 3600
    lastFetchTime: Optional[datetime] = None
    sourceCount: int = 0
    createdAt: datetime = field(default_factory=datetime.utcnow)
    updatedAt: datetime = field(default_factory=datetime.utcnow)

    def mark_fetched(self, source_count: int = 0):
        self.lastFetchTime = datetime.utcnow()
        self.sourceCount = source_count
        self.updatedAt = datetime.utcnow()


@dataclass
class FilterRule:
    """过滤规则领域实体"""
    id: int = 0
    name: str = ""
    group: Optional[str] = None
    pattern: str = ""
    replacement: str = ""
    isRegex: bool = True
    scope: Optional[str] = None  # sourceName, sourceUrl, sourceGroup, content
    isEnabled: bool = True
    order: int = 0
    createdAt: datetime = field(default_factory=datetime.utcnow)

    def should_filter(self, source_name: str = "", source_url: str = "", source_group: str = "", content: str = "") -> bool:
        """业务规则：判断规则是否匹配（返回 True 表示应该过滤掉）"""
        import re

        scope_map = {
            "sourceName": source_name,
            "sourceUrl": source_url,
            "sourceGroup": source_group,
            "content": content,
        }

        value = scope_map.get(self.scope or "sourceName", "")

        try:
            if self.isRegex:
                return bool(re.search(self.pattern, value))
            else:
                return self.pattern in value
        except re.error:
            return False
