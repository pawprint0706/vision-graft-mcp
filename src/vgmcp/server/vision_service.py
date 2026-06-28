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

    # External-transmission consent for cloud providers (plan §7.9).
    if not provider.is_local and not provider.consented:
        return {
            "status": "consent_required",
            "backend": provider.id,
            "provider_type": provider.type,
            "message": (
                f"'{provider.label or provider.id}'({provider.type})로 스크린샷을 외부 전송합니다. "
                "최초 1회 동의가 필요합니다."
            ),
            "next_action": (
                "사용자에게 외부 전송 동의를 받은 뒤, 트레이 '비전 백엔드 관리'의 해당 provider "
                f"동의 항목을 켜거나 `vgmcp provider consent {provider.id}`를 실행한 후 재시도하십시오. "
                "민감 화면이 우려되면 로컬 Ollama 백엔드를 사용할 수 있습니다."
            ),
        }

    api_key = None
    if not provider.is_local:
        api_key = credentials.get_key(provider.key_ref, provider_type=provider.type)

    try:
        backend = build_backend(provider, api_key)
    except VisionError as exc:
        return exc.to_result(provider.id)
    except Exception as exc:  # noqa: BLE001 — misconfig shouldn't crash the tool
        return {"status": "error", "backend": provider.id,
                "message": f"백엔드 초기화 실패: {exc}"}

    try:
        report = backend.analyze(image_path, prompt)
    except VisionError as exc:
        return exc.to_result(provider.id)
    except Exception as exc:  # noqa: BLE001 — surface unexpected failures as structured error
        from ..core.errors import VisionError as _VE, VisionErrorCode  # noqa: PLC0415

        return _VE(VisionErrorCode.UNKNOWN, f"예기치 못한 오류: {exc}").to_result(provider.id)

    # Success: last-used becomes the effective default going forward (plan §7.3).
    config.mark_used(provider.id)
    cfg.save_config(config)

    return VisionResult(backend=provider.id, report=report).model_dump()
