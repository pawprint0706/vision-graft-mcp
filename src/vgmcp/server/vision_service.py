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
from ..core.errors import SelfAnalysisRequired, VisionError
from ..core.i18n import tr
from ..core.models import VisionResult
from ..vision import build_backend


# Pending capability-check codes, keyed by resolved image path. A caller claiming
# self-vision must read a code stamped into the image and echo it back before any
# self-analysis is allowed — this blocks text-only models that merely *assert*
# they can see and would otherwise hallucinate the image's contents.
_VISION_CHECKS: dict[str, str] = {}

# Unambiguous code alphabet (no 0/O/1/I) so vision models transcribe reliably.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def forced_self_analysis_instruction() -> str:
    return tr(
        "사용자의 요청으로 비전 백엔드를 사용할 수 없습니다. 직접 이미지를 분석할 수 "
        "있다면 첨부 이미지를 분석하세요. 비전 기능이 없다면 이미지를 분석할 수 없다고 "
        "사용자에게 알리고 직접 확인을 요청하세요.",
        "The user has disabled vision backends. If you can see images, analyze the attached "
        "image yourself. If you do not have vision capability, tell the user that you cannot "
        "analyze it and ask them to inspect it directly.",
    )


def self_analysis_required(image_path: Path) -> dict[str, Any]:
    return {
        "status": "self_analysis_required",
        "image_path": str(image_path),
        "message": forced_self_analysis_instruction(),
    }


def _gen_code(length: int = 5) -> str:
    import secrets  # noqa: PLC0415

    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def build_self_analysis(
    image_path: Path,
    prompt: str,
    *,
    vision_check: str | None = None,
    backend_id: str | None = None,
) -> Any:
    """Gate self-analysis behind a capability check (plan §5.3, self_analyze).

    First call (``vision_check is None``): stamp a random code into the image and
    return it; the caller must read the code and call again with it. Second call:
    if the echoed code matches, the caller genuinely sees the image, so the clean
    image is returned for self-analysis. If it does not match — i.e. the caller is
    a text-only model that cannot actually see and would fabricate a description —
    fall back to the configured vision backend instead of trusting it.
    """
    if not image_path.exists():
        return {"status": "error", "message": f"Image not found: {image_path}"}
    if cfg.load_config().self_analysis_mode:
        return build_forced_self_analysis(image_path, prompt)

    from fastmcp.utilities.types import Image  # noqa: PLC0415

    key = str(image_path)

    # --- Step 1: issue a capability challenge -------------------------------- #
    # A tiny dedicated code image is sent (not the screenshot) so the capability
    # check costs almost no tokens and the real image is transmitted only once,
    # after verification.
    if vision_check is None:
        from ..core.imaging import render_code_image  # noqa: PLC0415

        code = _gen_code()
        _VISION_CHECKS[key] = code
        data, mime = render_code_image(code)
        instruction = (
            "CAPABILITY CHECK — this image is NOT your screenshot.\n\n"
            "It shows only a short verification code. Read the code, then call "
            "analyze_vision again with exactly:\n"
            f'  image_path   = "{image_path}"\n'
            "  self_analyze = true\n"
            '  vision_check = "<the code shown>"\n'
            "Your screenshot is returned for analysis only after the code matches.\n\n"
            "If you cannot read the code, then you are a text-only model and you "
            "cannot see images. Do NOT guess the code, and do NOT invent any "
            "description — fabricating vision is always treated as failure and "
            "gains you nothing. Instead, call analyze_vision again with "
            "self_analyze=false to route the image to the configured vision backend."
        )
        return [Image(data=data, format=mime.split("/", 1)[-1]), instruction]

    # --- Step 2: verify the echoed code ------------------------------------- #
    expected = _VISION_CHECKS.pop(key, None)
    if expected and vision_check.strip().upper() == expected:
        from ..core.imaging import preprocess  # noqa: PLC0415

        data, mime, _w, _h = preprocess(image_path)
        instruction = (
            "Verification passed — you can see this image. Analyze it yourself now "
            "and report concretely what you actually observe.\n\n"
            f"Task: {prompt}"
        )
        return [Image(data=data, format=mime.split("/", 1)[-1]), instruction]

    # Wrong/absent code: the caller cannot truly see the image. Do not let it
    # self-analyze — route to the real backend instead.
    return run_analysis(image_path, prompt, backend_id)


def build_forced_self_analysis(image_path: Path, prompt: str) -> Any:
    """Return the image directly to the caller without touching any backend."""
    if not image_path.exists():
        return {"status": "error", "message": f"Image not found: {image_path}"}

    from fastmcp.utilities.types import Image  # noqa: PLC0415
    from ..core.imaging import preprocess  # noqa: PLC0415

    config = cfg.load_config()
    try:
        data, mime, _w, _h = preprocess(
            image_path,
            max_long_edge=config.max_long_edge,
            downscale=config.downscale,
        )
    except Exception as exc:  # noqa: BLE001 — invalid images must not trigger backend fallback
        return {
            "status": "error",
            "code": "image_unreadable",
            "message": f"Cannot prepare image for self-analysis: {exc}",
        }

    instruction = (
        f"{forced_self_analysis_instruction()}\n\n"
        f"{tr('이미지 경로', 'Image path')}: {image_path}\n\n"
        f"{tr('분석 요청', 'Analysis request')}: {prompt}"
    )
    return [Image(data=data, format=mime.split("/", 1)[-1]), instruction]


def run_analysis(image_path: Path, prompt: str, backend_id: str | None) -> dict[str, Any]:
    config = cfg.load_config()

    if config.self_analysis_mode:
        return self_analysis_required(image_path)

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
    except SelfAnalysisRequired:
        return self_analysis_required(image_path)
    except VisionError as exc:
        return exc.to_result(provider.id)
    except Exception as exc:  # noqa: BLE001 — surface unexpected failures as structured error
        from ..core.errors import VisionError as _VE, VisionErrorCode  # noqa: PLC0415

        return _VE(VisionErrorCode.UNKNOWN, f"Unexpected error: {exc}").to_result(provider.id)

    # Success: last-used becomes the effective default going forward (plan §7.3).
    def mark_used(latest) -> None:
        if latest.get_provider(provider.id) is not None:
            latest.mark_used(provider.id)

    cfg.update_config(mark_used)

    return VisionResult(backend=provider.id, report=report).model_dump()
