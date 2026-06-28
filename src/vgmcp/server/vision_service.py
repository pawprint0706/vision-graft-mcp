"""analyze_vision orchestration (plan §5.3, §7).

Resolves the provider (explicit id or the effective default), resolves its key
from the credential store, runs the backend, updates last-used (plan §7.3), and
converts VisionError into the structured tool result (plan §7.8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import config as cfg
from ..core import credentials
from ..core.errors import VisionError
from ..core.models import VisionResult
from ..vision import build_backend


def run_analysis(image_path: Path, prompt: str, backend_id: str | None) -> dict[str, Any]:
    config = cfg.load_config()

    provider = (
        config.get_provider(backend_id) if backend_id else config.effective_default()
    )
    if provider is None:
        return {
            "status": "error",
            "message": (
                f"provider를 찾을 수 없습니다: {backend_id}"
                if backend_id
                else "등록된 비전 백엔드가 없습니다. check_environment를 호출하십시오."
            ),
        }

    api_key = None
    if not provider.is_local:
        api_key = credentials.get_key(provider.key_ref, provider_type=provider.type)

    try:
        backend = build_backend(provider, api_key)
    except VisionError as exc:
        return exc.to_result(provider.id)

    try:
        report = backend.analyze(image_path, prompt)
    except VisionError as exc:
        return exc.to_result(provider.id)

    # Success: last-used becomes the effective default going forward (plan §7.3).
    config.mark_used(provider.id)
    cfg.save_config(config)

    return VisionResult(backend=provider.id, report=report).model_dump()
