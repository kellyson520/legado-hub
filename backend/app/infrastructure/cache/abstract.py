"""
缓存抽象接口

设计原则：
- 领域层/应用层只依赖此接口
- 基础设施层提供 Redis/Memory 实现
- 小 VPS 默认使用内存缓存（零依赖）
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheProvider(ABC):
    """缓存提供者接口"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, expire: int = 3600) -> bool:
        """设置缓存值，expire 单位秒"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查 key 是否存在"""
        pass
    
    @abstractmethod
    async def increment(self, key: str, amount: int = 1, expire: int = 86400) -> int:
        """原子递增，返回新值"""
        pass
    
    @abstractmethod
    async def get_counter(self, key: str) -> int:
        """获取计数器值"""
        pass
    
    @abstractmethod
    async def reset_counter(self, key: str) -> bool:
        """重置计数器"""
        pass
