"""OpenAI-compatible vision backend (plan §7.2).

Serves OpenAI, OpenRouter, and custom OpenAI-compatible endpoints — they differ
only by base_url (and default model). Uses the chat/completions API with an
image_url data URI.
"""

from __future__ import annotations

import base64

import httpx

from ..core.errors import VisionError, VisionErrorCode
from ..core.models import ProviderConfig
from .base import BaseVisionBackend, map_httpx_error

_DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "openrouter": "openai/gpt-4o",
}
_MAX_TOKENS = 2048
_TIMEOUT = 60.0


class OpenAICompatibleBackend(BaseVisionBackend):
    def __init__(
        self, provider: ProviderConfig, api_key: str | None, *, base_url: str | None
    ) -> None:
        super().__init__(provider)
        self.api_key = api_key
        if not base_url:
            raise VisionError(
                VisionErrorCode.BAD_REQUEST,
                "custom provider에는 base_url이 필요합니다.",
            )
        self.base_url = base_url.rstrip("/")
        self.model = provider.model or _DEFAULT_MODELS.get(provider.type, "")

    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self.model)

    def _complete(self, image_bytes: bytes, mime: str, prompt: str) -> str:
        if not self.api_key:
            raise VisionError(VisionErrorCode.AUTH_FAILED, "API 키가 없습니다.")
        if not self.model:
            raise VisionError(VisionErrorCode.MODEL_NOT_FOUND, "모델명이 지정되지 않았습니다.")
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:{mime};base64,{b64}"
        body = {
            "model": self.model,
            "max_tokens": _MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers=headers,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise map_httpx_error(exc) from exc

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise VisionError(VisionErrorCode.RESPONSE_INVALID, "빈 응답을 받았습니다.")
        finish = choices[0].get("finish_reason")
        if finish == "content_filter":
            raise VisionError(VisionErrorCode.CONTENT_FILTERED, "안전 필터에 의해 차단되었습니다.")
        text = (choices[0].get("message") or {}).get("content") or ""
        if isinstance(text, list):  # some providers return content parts
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        if not text:
            raise VisionError(VisionErrorCode.RESPONSE_INVALID, "빈 응답을 받았습니다.")
        return text
