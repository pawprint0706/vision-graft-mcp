"""Anthropic Claude Vision backend (plan §7.2).

Uses the Messages API over httpx. Default model is a current vision-capable
Claude (claude-sonnet-4-6); override per provider via `model`.
"""

from __future__ import annotations

import base64

import httpx

from ..core.errors import VisionError, VisionErrorCode
from ..core.models import ProviderConfig
from .base import BaseVisionBackend, ensure_backend_allowed, map_httpx_error

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2048
_TIMEOUT = 60.0


class AnthropicBackend(BaseVisionBackend):
    def __init__(self, provider: ProviderConfig, api_key: str | None) -> None:
        super().__init__(provider)
        self.api_key = api_key
        self.model = provider.model or _DEFAULT_MODEL

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _complete(self, image_bytes: bytes, mime: str, prompt: str) -> str:
        if not self.api_key:
            raise VisionError(VisionErrorCode.AUTH_FAILED, "Missing Anthropic API key.")
        b64 = base64.b64encode(image_bytes).decode("ascii")
        body = {
            "model": self.model,
            "max_tokens": _MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": mime, "data": b64},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        try:
            ensure_backend_allowed()
            resp = httpx.post(_API_URL, json=body, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise map_httpx_error(exc) from exc

        data = resp.json()
        if data.get("stop_reason") == "refusal":
            raise VisionError(VisionErrorCode.CONTENT_FILTERED, "The model refused to respond.")
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        if not text:
            raise VisionError(VisionErrorCode.RESPONSE_INVALID, "Received an empty response.")
        return text
