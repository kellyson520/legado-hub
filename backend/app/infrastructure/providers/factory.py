from __future__ import annotations

from typing import Any

from app.application.ports.provider import SUPPORTED_PROVIDER_TYPES


def create_provider_adapter(
    name: str,
    endpoint_url: str,
    api_key: str,
    provider_type: str = "openai_compatible",
    **kwargs: Any,
):
    normalized = str(provider_type or "openai_compatible").strip().lower()
    if normalized not in SUPPORTED_PROVIDER_TYPES:
        raise ValueError(f"unsupported provider type: {normalized}")
    if normalized == "openai_compatible":
        from .openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(name, endpoint_url, api_key, **kwargs)
    if normalized == "anthropic":
        from .anthropic import AnthropicProvider

        return AnthropicProvider(name, endpoint_url, api_key, **kwargs)
    from .gemini import GeminiProvider

    return GeminiProvider(name, endpoint_url, api_key, **kwargs)
