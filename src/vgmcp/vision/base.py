"""Base vision backend: preprocessing + prompt + staged parse fallback (§7.5/§7.7).

Subclasses implement `_complete(image_bytes, mime, prompt) -> str` and
`is_configured()`, mapping transport errors to `VisionError` (§7.8).
"""

from __future__ import annotations

import httpx

from pathlib import Path

from ..core.config import load_config
from ..core.errors import VisionError, VisionErrorCode
from ..core.imaging import preprocess
from ..core.interfaces import VisionBackend
from ..core.models import ProviderConfig, VisionReportBody
from . import report as report_mod


class BaseVisionBackend(VisionBackend):
    def __init__(self, provider: ProviderConfig) -> None:
        self.provider = provider
        self.backend_id = provider.id

    # ---- subclass hooks ---------------------------------------------------- #
    def _complete(self, image_bytes: bytes, mime: str, prompt: str) -> str:
        raise NotImplementedError

    def is_configured(self) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    # ---- shared pipeline --------------------------------------------------- #
    def analyze(self, image_path: Path, prompt: str) -> VisionReportBody:
        if not image_path.exists():
            raise VisionError(
                VisionErrorCode.BAD_REQUEST, f"이미지 파일이 존재하지 않습니다: {image_path}"
            )
        cfg = load_config()
        image_bytes, mime, _w, _h = preprocess(
            image_path, max_long_edge=cfg.max_long_edge, downscale=cfg.downscale
        )

        full_prompt = prompt + report_mod.SCHEMA_INSTRUCTION
        raw = self._complete(image_bytes, mime, full_prompt)

        parsed = report_mod.try_parse(raw)
        if parsed is not None:
            return parsed

        # One corrective retry (plan §7.7 step 3).
        corrective = report_mod.CORRECTIVE_INSTRUCTION + raw + report_mod.SCHEMA_INSTRUCTION
        try:
            raw2 = self._complete(image_bytes, mime, corrective)
        except VisionError:
            return report_mod.degraded(raw)
        parsed2 = report_mod.try_parse(raw2)
        if parsed2 is not None:
            return parsed2

        # Lossless fallback (plan §7.7 step 4).
        return report_mod.degraded(raw2 or raw)


def map_httpx_error(exc: Exception) -> VisionError:
    """Translate an httpx exception into a VisionError (plan §7.8.1)."""
    if isinstance(exc, httpx.TimeoutException):
        return VisionError(VisionErrorCode.TIMEOUT, str(exc) or "요청 시간 초과")
    if isinstance(exc, httpx.HTTPStatusError):
        return map_status(exc.response.status_code, exc)
    if isinstance(exc, httpx.HTTPError):
        return VisionError(VisionErrorCode.NETWORK, str(exc) or "네트워크 오류")
    return VisionError(VisionErrorCode.UNKNOWN, str(exc) or "알 수 없는 오류")


def map_status(status: int, exc: Exception | None = None) -> VisionError:
    msg = str(exc) if exc else f"HTTP {status}"
    retry_after = None
    if exc is not None and isinstance(exc, httpx.HTTPStatusError):
        ra = exc.response.headers.get("retry-after")
        if ra:
            try:
                retry_after = float(ra)
            except ValueError:
                retry_after = None
    code = {
        400: VisionErrorCode.BAD_REQUEST,
        401: VisionErrorCode.AUTH_FAILED,
        402: VisionErrorCode.QUOTA_EXCEEDED,
        403: VisionErrorCode.AUTH_FAILED,
        404: VisionErrorCode.MODEL_NOT_FOUND,
        413: VisionErrorCode.BAD_REQUEST,
        415: VisionErrorCode.BAD_REQUEST,
        422: VisionErrorCode.BAD_REQUEST,
        429: VisionErrorCode.RATE_LIMIT,
    }.get(status)
    if code is None:
        code = VisionErrorCode.SERVER_ERROR if status >= 500 else VisionErrorCode.UNKNOWN
    return VisionError(code, msg, http_status=status, retry_after_sec=retry_after)
