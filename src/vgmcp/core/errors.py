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
    VisionErrorCode.AUTH_FAILED: "트레이 '비전 백엔드 관리'에서 API 키를 확인·재등록하십시오.",
    VisionErrorCode.RATE_LIMIT: "잠시 후(retry_after_sec) 재시도하거나 다른 백엔드를 지정하십시오.",
    VisionErrorCode.QUOTA_EXCEEDED: "결제/플랜을 확인하거나 로컬(Ollama) 백엔드로 전환하십시오.",
    VisionErrorCode.TIMEOUT: "재시도하고, 지속되면 이미지를 축소하거나 다른 백엔드를 사용하십시오.",
    VisionErrorCode.NETWORK: "네트워크 연결을 확인 후 재시도하십시오(로컬 백엔드는 영향이 적습니다).",
    VisionErrorCode.SERVER_ERROR: "잠시 후 재시도하거나 다른 백엔드를 지정하십시오.",
    VisionErrorCode.BAD_REQUEST: "모델명/이미지 형식·크기를 점검하십시오(전처리 재확인).",
    VisionErrorCode.CONTENT_FILTERED: "프롬프트/이미지를 조정하거나 다른 백엔드를 사용하십시오.",
    VisionErrorCode.MODEL_NOT_FOUND: "provider 설정에서 모델명을 수정하십시오.",
    VisionErrorCode.OLLAMA_UNAVAILABLE: "'ollama serve' 기동 및 'ollama pull <model>' 후 재시도하십시오.",
    VisionErrorCode.RESPONSE_INVALID: "재시도하거나 다른 백엔드를 사용하십시오.",
    VisionErrorCode.UNKNOWN: "재시도하고, 지속되면 로그를 첨부해 보고하십시오.",
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
