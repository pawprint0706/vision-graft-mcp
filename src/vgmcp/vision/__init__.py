"""Vision backends (plan §7).

`build_backend(provider, api_key)` constructs the concrete backend for a
registered provider. OpenAI / OpenRouter / custom share one OpenAI-compatible
client differing only by base_url (plan §7.2).
"""

from __future__ import annotations

from ..core.config import DEFAULT_BASE_URLS, DEFAULT_OLLAMA_HOST
from ..core.interfaces import VisionBackend
from ..core.models import ProviderConfig


def build_backend(provider: ProviderConfig, api_key: str | None) -> VisionBackend:
    if provider.type == "anthropic":
        from .anthropic_backend import AnthropicBackend  # noqa: PLC0415

        return AnthropicBackend(provider, api_key)
    if provider.type in ("openai", "openrouter", "custom"):
        from .openai_backend import OpenAICompatibleBackend  # noqa: PLC0415

        base_url = provider.base_url or DEFAULT_BASE_URLS.get(provider.type)
        return OpenAICompatibleBackend(provider, api_key, base_url=base_url)
    if provider.type == "ollama":
        from .ollama_backend import OllamaBackend  # noqa: PLC0415

        return OllamaBackend(provider, host=provider.base_url or DEFAULT_OLLAMA_HOST)
    raise ValueError(f"unknown provider type: {provider.type}")
