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
                f"Provider not found: {backend_id}"
                if backend_id
                else "No vision backend registered. Call check_environment."
            ),
        }

    # External-transmission consent for cloud providers (plan §7.9).
    if not provider.is_local and not provider.consented:
        return {
            "status": "consent_required",
            "backend": provider.id,
            "provider_type": provider.type,
            "message": (
                f"Screenshots will be sent externally to '{provider.label or provider.id}'"
                f"({provider.type}). One-time consent is required."
            ),
            "next_action": (
                "Get the user's consent to send screenshots externally, then enable consent for "
                f"this provider in tray 'Manage vision backends' or run "
                f"`vgmcp provider consent {provider.id}`, and retry. "
                "If sensitive screens are a concern, use the local Ollama backend."
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
                "message": f"Backend init failed: {exc}"}

    try:
        report = backend.analyze(image_path, prompt)
    except VisionError as exc:
        return exc.to_result(provider.id)
    except Exception as exc:  # noqa: BLE001 — surface unexpected failures as structured error
        from ..core.errors import VisionError as _VE, VisionErrorCode  # noqa: PLC0415

        return _VE(VisionErrorCode.UNKNOWN, f"Unexpected error: {exc}").to_result(provider.id)

    # Success: last-used becomes the effective default going forward (plan §7.3).
    config.mark_used(provider.id)
    cfg.save_config(config)

    return VisionResult(backend=provider.id, report=report).model_dump()
