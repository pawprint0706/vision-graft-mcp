"""Local Ollama vision backend (plan §7.2).

No API key, no external transmission (plan §7.9). Talks to the local Ollama
REST API (/api/chat). A connection error maps to OLLAMA_UNAVAILABLE.
"""

from __future__ import annotations

import base64

import httpx

from ..core.errors import VisionError, VisionErrorCode
from ..core.models import ProviderConfig
from .base import BaseVisionBackend, map_httpx_error

_DEFAULT_MODEL = "llava"
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
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
        }
        try:
            resp = httpx.post(f"{self.host}/api/chat", json=body, timeout=_TIMEOUT)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise VisionError(
                VisionErrorCode.OLLAMA_UNAVAILABLE,
                f"Cannot connect to the local Ollama server ({self.host}).",
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise VisionError(
                    VisionErrorCode.OLLAMA_UNAVAILABLE,
                    f"Model '{self.model}' not found. Run 'ollama pull {self.model}' and retry.",
                    http_status=404,
                ) from exc
            raise map_httpx_error(exc) from exc
        except httpx.HTTPError as exc:
            raise map_httpx_error(exc) from exc

        data = resp.json()
        text = (data.get("message") or {}).get("content") or ""
        if not text:
            raise VisionError(VisionErrorCode.RESPONSE_INVALID, "Received an empty response.")
        return text
