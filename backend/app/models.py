from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# ==================== BookSource Models ====================

class BookInfoRule(BaseModel):
    init: Optional[str] = None
    name: Optional[str] = None
    author: Optional[str] = None
    intro: Optional[str] = None
    kind: Optional[str] = None
    lastChapter: Optional[str] = None
    updateTime: Optional[str] = None
    coverUrl: Optional[str] = None
    tocUrl: Optional[str] = None
    wordCount: Optional[str] = None
    canReName: Optional[str] = None
    initToc: Optional[str] = None

class SearchRule(BaseModel):
    checkKeyWord: Optional[str] = None
    bookList: Optional[str] = None
    name: Optional[str] = None
    author: Optional[str] = None
    kind: Optional[str] = None
    wordCount: Optional[str] = None
    lastChapter: Optional[str] = None
    intro: Optional[str] = None
    coverUrl: Optional[str] = None
    bookUrl: Optional[str] = None

class ExploreRule(BaseModel):
    bookList: Optional[str] = None
    name: Optional[str] = None
    author: Optional[str] = None
    kind: Optional[str] = None
    wordCount: Optional[str] = None
    lastChapter: Optional[str] = None
    intro: Optional[str] = None
    coverUrl: Optional[str] = None
    bookUrl: Optional[str] = None

class TocRule(BaseModel):
    preUpdateJs: Optional[str] = None
    chapterList: Optional[str] = None
    chapterName: Optional[str] = None
    chapterUrl: Optional[str] = None
    isVip: Optional[str] = None
    updateTime: Optional[str] = None
    nextTocUrl: Optional[str] = None

class ContentRule(BaseModel):
    content: Optional[str] = None
    title: Optional[str] = None
    nextContentUrl: Optional[str] = None
    webJs: Optional[str] = None
    sourceRegex: Optional[str] = None
    replaceRegex: Optional[str] = None
    imageStyle: Optional[str] = None
    imageDecode: Optional[str] = None

class BookSource(BaseModel):
    bookSourceUrl: str
    bookSourceName: str
    bookSourceGroup: Optional[str] = None
    bookSourceType: int = 0
    bookUrlPattern: Optional[str] = None
    customOrder: int = 0
    enabled: bool = True
    enabledExplore: bool = True
    jsLib: Optional[str] = None
    enabledCookieJar: Optional[bool] = True
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
    ruleExplore: Optional[ExploreRule] = None
    searchUrl: Optional[str] = None
    ruleSearch: Optional[SearchRule] = None
    ruleBookInfo: Optional[BookInfoRule] = None
    ruleToc: Optional[TocRule] = None
    ruleContent: Optional[ContentRule] = None
    ruleReview: Optional[Any] = None
    eventListener: bool = False
    customButton: bool = False
    homepageModules: Optional[str] = None
    # hub fields
    sourceStatus: Optional[str] = "unknown"
    lastCheckTime: Optional[datetime] = None
    errorMsg: Optional[str] = None
    sourceOrigin: Optional[str] = None

# ==================== RssSource Models ====================

class RssSource(BaseModel):
    sourceUrl: str
    sourceName: str
    sourceIcon: Optional[str] = None
    sourceGroup: Optional[str] = None
    sourceComment: Optional[str] = None
    enabled: bool = True
    variableComment: Optional[str] = None
    jsLib: Optional[str] = None
    enabledCookieJar: Optional[bool] = True
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
    # hub fields
    sourceStatus: Optional[str] = "unknown"
    lastCheckTime: Optional[datetime] = None
    errorMsg: Optional[str] = None
    sourceOrigin: Optional[str] = None

# ==================== FilterRule Models ====================

class FilterRule(BaseModel):
    id: Optional[int] = None
    name: str
    group: Optional[str] = None
    pattern: str
    replacement: str = ""
    isRegex: bool = True
    scope: Optional[str] = None
    isEnabled: bool = True
    order: int = 0

class FilterRuleCreate(BaseModel):
    name: str
    group: Optional[str] = None
    pattern: str
    replacement: str = ""
    isRegex: bool = True
    scope: Optional[str] = "sourceName"
    isEnabled: bool = True
    order: int = 0

# ==================== Subscription Models ====================

class Subscription(BaseModel):
    id: Optional[int] = None
    name: str
    url: str
    subType: str = "book"
    enabled: bool = True
    autoFetch: bool = True
    fetchInterval: int = 3600
    lastFetchTime: Optional[datetime] = None
    sourceCount: int = 0

class SubscriptionCreate(BaseModel):
    name: str
    url: str
    subType: str = "book"
    autoFetch: bool = True
    fetchInterval: int = 3600

# ==================== Engine / Generator Models ====================

class GenerateSourceRequest(BaseModel):
    url: str
    sourceType: str = "rss"  # book, rss
    sourceName: Optional[str] = None

class GeneratedSourceResult(BaseModel):
    success: bool
    source: Optional[Dict[str, Any]] = None
    message: str = ""
    logs: List[str] = []

# ==================== Health Check Models ====================

class HealthCheckResult(BaseModel):
    sourceUrl: str
    sourceName: str
    sourceType: str
    status: str  # ok, error
    responseTime: float = 0.0
    errorMsg: Optional[str] = None
    checkedAt: datetime = Field(default_factory=datetime.utcnow)

class UnifiedOutput(BaseModel):
    bookSources: List[Dict[str, Any]] = []
    rssSources: List[Dict[str, Any]] = []
    generatedAt: datetime = Field(default_factory=datetime.utcnow)
    totalBookSources: int = 0
    totalRssSources: int = 0

# ==================== Response Models ====================

class ApiResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[Any] = None

class PaginatedResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: List[Any] = []
    total: int = 0
    page: int = 1
    pageSize: int = 20
