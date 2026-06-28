"""Error taxonomy (plan §7.8.1).

`VisionError` is raised by vision backends on runtime failures (config is fine,
the call failed). The server layer converts it into the structured
`status: "vision_error"` tool result.
"""

from __future__ import annotations

from enum import Enum


class VisionErrorCode(str, Enum):
    """Vision runtime error codes (plan §7.8.1)."""

    AUTH_FAILED = "AUTH_FAILED"            # 401/403 — invalid/expired key
    RATE_LIMIT = "RATE_LIMIT"             # 429
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"     # 402 / billing exhausted
    TIMEOUT = "TIMEOUT"                   # client timeout
    NETWORK = "NETWORK"                   # connection/DNS/offline
    SERVER_ERROR = "SERVER_ERROR"        # provider 5xx
    BAD_REQUEST = "BAD_REQUEST"          # 400/413/415/422 — model/image issue
    CONTENT_FILTERED = "CONTENT_FILTERED"  # safety filter blocked
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"  # 404 / unknown model
    OLLAMA_UNAVAILABLE = "OLLAMA_UNAVAILABLE"  # local server down / model missing
    RESPONSE_INVALID = "RESPONSE_INVALID"  # got a response but unusable (fallback impossible)
    UNKNOWN = "UNKNOWN"                   # unclassified

    @property
    def retryable(self) -> bool:
        return self in _RETRYABLE


_RETRYABLE: frozenset[VisionErrorCode] = frozenset(
    {
        VisionErrorCode.RATE_LIMIT,
        VisionErrorCode.TIMEOUT,
        VisionErrorCode.NETWORK,
        VisionErrorCode.SERVER_ERROR,
        VisionErrorCode.OLLAMA_UNAVAILABLE,
        VisionErrorCode.RESPONSE_INVALID,
        VisionErrorCode.UNKNOWN,
    }
)


# Default human guidance per code (plan §7.8.1 "권장 next_action").
NEXT_ACTION: dict[VisionErrorCode, str] = {
    VisionErrorCode.AUTH_FAILED: "Check/re-enter the API key in the tray 'Manage vision backends'.",
    VisionErrorCode.RATE_LIMIT: "Retry after retry_after_sec, or specify a different backend.",
    VisionErrorCode.QUOTA_EXCEEDED: "Check billing/plan, or switch to the local (Ollama) backend.",
    VisionErrorCode.TIMEOUT: "Retry; if it persists, downscale the image or use another backend.",
    VisionErrorCode.NETWORK: "Check the network and retry (local backends are unaffected).",
    VisionErrorCode.SERVER_ERROR: "Retry shortly, or specify a different backend.",
    VisionErrorCode.BAD_REQUEST: "Check the model name and image format/size (review preprocessing).",
    VisionErrorCode.CONTENT_FILTERED: "Adjust the prompt/image, or use another backend.",
    VisionErrorCode.MODEL_NOT_FOUND: "Fix the model name in the provider settings.",
    VisionErrorCode.OLLAMA_UNAVAILABLE: "Start 'ollama serve' and 'ollama pull <model>', then retry.",
    VisionErrorCode.RESPONSE_INVALID: "Retry, or use another backend.",
    VisionErrorCode.UNKNOWN: "Retry; if it persists, report with logs attached.",
}


class VGMCPError(Exception):
    """Base class for all VGMCP errors."""


class VisionError(VGMCPError):
    """A vision backend call failed at runtime (plan §7.8)."""

    def __init__(
        self,
        code: VisionErrorCode,
        message: str,
        *,
        http_status: int | None = None,
        retry_after_sec: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retry_after_sec = retry_after_sec

    def to_result(self, backend: str) -> dict:
        """Serialize to the structured tool result (plan §7.8)."""
        return {
            "status": "vision_error",
            "backend": backend,
            "error_code": self.code.value,
            "retryable": self.code.retryable,
            "retry_after_sec": self.retry_after_sec,
            "http_status": self.http_status,
            "message": self.message,
            "next_action": NEXT_ACTION[self.code],
        }


class CaptureError(VGMCPError):
    """Screen capture failed."""
