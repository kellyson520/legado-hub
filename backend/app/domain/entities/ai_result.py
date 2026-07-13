"""
AI 分析结果领域实体
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class AICharacterResult:
    """人物关系分析结果"""
    id: int = 0
    book_url: str = ""
    book_name: Optional[str] = None
    characters_json: Dict[str, Any] = field(default_factory=dict)
    graph_data: Optional[Dict[str, Any]] = None
    created_by: Optional[int] = None
    createdAt: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AIWorldResult:
    """世界观分析结果"""
    id: int = 0
    book_url: str = ""
    book_name: Optional[str] = None
    world_json: Dict[str, Any] = field(default_factory=dict)
    created_by: Optional[int] = None
    createdAt: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AIStorylineResult:
    """剧情时间线分析结果"""
    id: int = 0
    book_url: str = ""
    book_name: Optional[str] = None
    timeline_json: Dict[str, Any] = field(default_factory=dict)
    created_by: Optional[int] = None
    createdAt: datetime = field(default_factory=datetime.utcnow)
