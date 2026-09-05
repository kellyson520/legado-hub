"""
书源基础设施 - Source Engine

书源的定义、发现、验证、管理。
上层书源技能通过统一接口调用。

书源格式（参考 Legado）：
- bookSourceUrl: 书源地址
- bookSourceName: 书源名称
- bookSourceGroup: 书源分组
- bookSourceType: 0 文本 / 1 音频 / 2 图片
- ruleSearchUrl: 搜索规则
- ruleBookList: 书籍列表规则
- ruleBookName: 书名规则
- ruleBookAuthor: 作者规则
- ruleCoverUrl: 封面规则
- ruleContentUrl: 正文链接规则
- ruleBookContent: 正文内容规则
- ruleChapterUrl: 章节目录规则
- ruleChapterName: 章节名称规则
"""

from __future__ import annotations

import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict


@dataclass
class BookSource:
    """书源数据结构（兼容 Legado 格式）"""
    bookSourceName: str = ""
    bookSourceUrl: str = ""
    bookSourceGroup: str = ""
    bookSourceType: int = 0  # 0: text, 1: audio, 2: image
    bookSourceComment: str = ""
    lastUpdateTime: int = 0

    ruleSearchUrl: str = ""
    ruleSearchList: str = ""
    ruleSearchName: str = ""
    ruleSearchAuthor: str = ""
    ruleSearchCover: str = ""
    ruleSearchNote: str = ""
    ruleSearchResultUrl: str = ""

    ruleBookUrlPattern: str = ""
    ruleBookName: str = ""
    ruleBookAuthor: str = ""
    ruleBookCover: str = ""
    ruleBookIntro: str = ""
    ruleBookKind: str = ""
    ruleBookLastChapter: str = ""
    ruleBookUpdateTime: str = ""

    ruleChapterUrl: str = ""
    ruleChapterName: str = ""
    ruleChapterIsUrl: str = ""

    ruleContentUrl: str = ""
    ruleContent: str = ""

    header: str = ""
    loginUrl: str = ""
    loginUi: str = ""
    loginCheckJs: str = ""
    variableComment: str = ""
    commentUrl: str = ""
    exploreUrl: str = ""
    bookSourceIcon: str = ""
    enabled: bool = True
    enabledExplore: bool = False
    enabledCookieJar: bool = False
    concurrentRate: str = ""
    jsLib: str = ""
    loadWithBaseUrl: bool = False
    sourceTag: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BookSource":
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def validate(self) -> Tuple[bool, List[str]]:
        """验证书源有效性"""
        errors = []
        if not self.bookSourceName:
            errors.append("缺少书源名称")
        if not self.bookSourceUrl:
            errors.append("缺少书源地址")
        if not self.ruleSearchUrl:
            errors.append("缺少搜索规则")
        if not self.ruleChapterName:
            errors.append("缺少章节名称规则")
        if not self.ruleContent:
            errors.append("缺少正文内容规则")
        return len(errors) == 0, errors


class SourceEngine:
    """书源引擎 - 底层基础设施

    能力：
    - 书源 CRUD 管理
    - 书源发现（搜索书源）
    - 书源验证（可用性检测）
    - 书源格式转换（Legado / 自定义）
    - 书源评分排序
    """

    def __init__(self, storage_path: str = "data/book_sources.json"):
        self.storage_path = storage_path
        self._sources: List[BookSource] = []
        self._load()

    def _load(self):
        import os
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._sources = [BookSource.from_dict(s) for s in data]
            except Exception:
                self._sources = []

    def _save(self):
        import os
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(
                [s.to_dict() for s in self._sources],
                f, ensure_ascii=False, indent=2
            )

    def add_source(self, source: BookSource) -> bool:
        """添加书源"""
        # 检查重复
        for s in self._sources:
            if s.bookSourceUrl == source.bookSourceUrl:
                return False
        self._sources.append(source)
        self._save()
        return True

    def remove_source(self, bookSourceUrl: str) -> bool:
        """删除书源"""
        for i, s in enumerate(self._sources):
            if s.bookSourceUrl == bookSourceUrl:
                del self._sources[i]
                self._save()
                return True
        return False

    def get_source(self, bookSourceUrl: str) -> Optional[BookSource]:
        """获取书源"""
        for s in self._sources:
            if s.bookSourceUrl == bookSourceUrl:
                return s
        return None

    def list_sources(
        self,
        group: str = "",
        source_type: Optional[int] = None,
        enabled_only: bool = True,
        keyword: str = "",
    ) -> List[BookSource]:
        """列出书源"""
        results = self._sources
        if enabled_only:
            results = [s for s in results if s.enabled]
        if group:
            results = [s for s in results if s.bookSourceGroup == group]
        if source_type is not None:
            results = [s for s in results if s.bookSourceType == source_type]
        if keyword:
            kw = keyword.lower()
            results = [
                s for s in results
                if kw in s.bookSourceName.lower()
                or kw in s.bookSourceUrl.lower()
            ]
        return results

    def list_groups(self) -> List[str]:
        """列出所有分组"""
        groups = set()
        for s in self._sources:
            if s.bookSourceGroup:
                groups.add(s.bookSourceGroup)
        return sorted(groups)

    def validate_source(self, source: BookSource) -> Tuple[bool, List[str]]:
        """验证书源"""
        return source.validate()

    def generate_source_template(self, source_type: str = "text") -> BookSource:
        """生成书源模板"""
        type_map = {"text": 0, "audio": 1, "image": 2}
        return BookSource(
            bookSourceName="新书源",
            bookSourceUrl="https://",
            bookSourceGroup="未分组",
            bookSourceType=type_map.get(source_type, 0),
            ruleSearchUrl="",
            ruleChapterName="",
            ruleContent="",
        )

    def import_from_json(self, json_data: str) -> int:
        """从 JSON 导入书源"""
        try:
            data = json.loads(json_data)
            if isinstance(data, list):
                count = 0
                for item in data:
                    source = BookSource.from_dict(item)
                    if self.add_source(source):
                        count += 1
                return count
        except Exception:
            pass
        return 0

    def export_to_json(self, sources: Optional[List[BookSource]] = None) -> str:
        """导出为 JSON"""
        if sources is None:
            sources = self._sources
        return json.dumps(
            [s.to_dict() for s in sources],
            ensure_ascii=False, indent=2
        )

    @property
    def count(self) -> int:
        return len(self._sources)


_source_singleton: Optional[SourceEngine] = None


def source_engine(storage_path: str = "data/book_sources.json") -> SourceEngine:
    """获取书源引擎单例"""
    global _source_singleton
    if _source_singleton is None:
        _source_singleton = SourceEngine(storage_path=storage_path)
    return _source_singleton
