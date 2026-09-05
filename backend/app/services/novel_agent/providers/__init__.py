"""
LLM Provider 抽象层
参考 DeepSeek-Reasonix 的 Provider 接口设计
支持多模型、多 Provider 注册
"""
from __future__ import annotations

import os
import json
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional, Any
from dataclasses import dataclass, field


class ProviderError(RuntimeError):
    """Base error for the legacy provider surface."""


class ProviderHTTPError(ProviderError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = int(status_code)
        self.retryable = self.status_code in {408, 409, 425, 429, 500, 502, 503, 504}


class ProviderStreamError(ProviderError):
    def __init__(self, message: str, *, cause: BaseException | None = None):
        super().__init__(message)
        self.cause = cause


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class Message:
    role: str
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hit_tokens + self.cache_miss_tokens
        if total == 0:
            return 0.0
        return self.cache_hit_tokens / total


@dataclass
class StreamChunk:
    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: Optional[Usage] = None
    error: Optional[str] = None
    exception: Optional[BaseException] = None
    done: bool = False


@dataclass
class ProviderConfig:
    name: str
    kind: str = "openai"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    api_key_env: str = ""
    context_window: int = 128000
    extra: Dict[str, str] = field(default_factory=dict)

    def get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return ""


class BaseProvider(ABC):
    """Provider 抽象基类"""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def context_window(self) -> int:
        return self.config.context_window

    @abstractmethod
    def stream(self, messages: List[Message], system: str = "",
               tools: Optional[List[ToolSchema]] = None,
               temperature: float = 0.7, max_tokens: int = 4096) -> AsyncIterator[StreamChunk]:
        """流式生成"""
        ...

    @abstractmethod
    def complete(self, messages: List[Message], system: str = "",
                 tools: Optional[List[ToolSchema]] = None,
                 temperature: float = 0.7, max_tokens: int = 4096) -> tuple[str, List[ToolCall], Usage]:
        """非流式生成"""
        ...


class ProviderRegistry:
    """Provider 注册表"""

    _factories: Dict[str, type] = {}
    _instances: Dict[str, BaseProvider] = {}

    @classmethod
    def register(cls, kind: str, factory_cls: type):
        cls._factories[kind] = factory_cls

    @classmethod
    def create(cls, config: ProviderConfig) -> BaseProvider:
        if config.name in cls._instances:
            return cls._instances[config.name]

        factory_cls = cls._factories.get(config.kind)
        if not factory_cls:
            raise ValueError(f"Unknown provider kind: {config.kind}")

        provider = factory_cls(config)
        cls._instances[config.name] = provider
        return provider

    @classmethod
    def get(cls, name: str) -> Optional[BaseProvider]:
        return cls._instances.get(name)

    @classmethod
    def clear(cls):
        cls._instances.clear()


def register_provider(kind: str):
    """Provider 注册装饰器"""
    def decorator(cls):
        ProviderRegistry.register(kind, cls)
        return cls
    return decorator


# Import built-in adapters so their decorators register them for the legacy runtime.
from . import openai_provider as _openai_provider  # noqa: E402,F401
