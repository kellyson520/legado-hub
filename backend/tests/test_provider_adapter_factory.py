def test_provider_adapter_factory_selects_openai_anthropic_and_gemini():
    from app.infrastructure.providers.anthropic import AnthropicProvider
    from app.infrastructure.providers.factory import create_provider_adapter
    from app.infrastructure.providers.gemini import GeminiProvider
    from app.infrastructure.providers.openai_compatible import OpenAICompatibleProvider

    openai = create_provider_adapter("openai", "https://openai.test/v1", "key", "openai_compatible")
    anthropic = create_provider_adapter("anthropic", "https://anthropic.test", "key", "anthropic")
    gemini = create_provider_adapter("gemini", "https://gemini.test", "key", "gemini")

    assert isinstance(openai, OpenAICompatibleProvider)
    assert isinstance(anthropic, AnthropicProvider)
    assert isinstance(gemini, GeminiProvider)


def test_provider_adapter_factory_rejects_unknown_provider_type():
    import pytest

    from app.infrastructure.providers.factory import create_provider_adapter

    with pytest.raises(ValueError, match="unsupported provider type"):
        create_provider_adapter("unknown", "https://provider.test", "key", "unknown")
