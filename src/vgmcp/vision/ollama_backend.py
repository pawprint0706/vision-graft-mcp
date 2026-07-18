"""Local Ollama vision backend (plan §7.2).

No API key, no external transmission (plan §7.9). Talks to the local Ollama
REST API (/api/chat). A connection error maps to OLLAMA_UNAVAILABLE.
"""

from __future__ import annotations

import base64

import httpx

from ..core.errors import VisionError, VisionErrorCode
from ..core.models import ProviderConfig
from .base import BaseVisionBackend, ensure_backend_allowed, map_httpx_error

_DEFAULT_MODEL = "llava:7b"
_TIMEOUT = 180.0  # local inference can be slow


class OllamaBackend(BaseVisionBackend):
    def __init__(self, provider: ProviderConfig, *, host: str) -> None:
        super().__init__(provider)
        self.host = host.rstrip("/")
        self.model = provider.model or _DEFAULT_MODEL

    def is_configured(self) -> bool:
        return True  # local; configured-ness is checked at call time

    def _complete(self, image_bytes: bytes, mime: str, prompt: str) -> str:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        body = {
            "model": self.model,
            "stream": False,
            "format": "json",  # ask Ollama for JSON output (plan §7.7)
            # Reasoning models (e.g. qwen3-vl) default to thinking ON, which sends
            # the whole answer to message.thinking and leaves message.content empty
            # (or just "{}"). Turn it off so the answer lands in content.
            "think": False,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
        }
        data = self._chat(body)
        message = data.get("message") or {}
        text = message.get("content") or ""
        if not text.strip():
            # Safety net: a reasoning model may still have put text in `thinking`.
            text = (message.get("thinking") or "").strip()
        if not text.strip():
            raise VisionError(VisionErrorCode.RESPONSE_INVALID, "Received an empty response.")
        return text

    def _chat(self, body: dict) -> dict:
        try:
            ensure_backend_allowed()
            resp = httpx.post(f"{self.host}/api/chat", json=body, timeout=_TIMEOUT)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise VisionError(
                VisionErrorCode.OLLAMA_UNAVAILABLE,
                f"Cannot connect to the local Ollama server ({self.host}).",
            ) from exc
        except httpx.HTTPStatusError as exc:
            # Non-reasoning models / older Ollama may reject the `think` field with
            # a 400. Retry once without it (text-independent, since the exact error
            # wording varies by version) so plain VLMs like llava still work.
            if "think" in body and exc.response.status_code == 400:
                return self._chat({k: v for k, v in body.items() if k != "think"})
            if exc.response.status_code == 404:
                raise VisionError(
                    VisionErrorCode.OLLAMA_UNAVAILABLE,
                    f"Model '{self.model}' not found. Run 'ollama pull {self.model}' and retry.",
                    http_status=404,
                ) from exc
            raise map_httpx_error(exc) from exc
        except httpx.HTTPError as exc:
            raise map_httpx_error(exc) from exc

        return resp.json()
