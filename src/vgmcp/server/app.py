"""FastMCP app + tool definitions (plan §5).

Tools are thin: they run the lazy environment check (plan §3.2.1.2), then call
shared core logic. On an incomplete environment they return the structured
guide (plan §3.3.2) instead of raising.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from ..core import config as cfg
from ..core.environment import EnvironmentChecker

mcp: FastMCP = FastMCP(
    name="vgmcp",
    instructions=(
        "Vision-Graft MCP gives you an 'eye'. When you modify frontend code or "
        "the user reports a UI issue, capture the screen with take_screenshot, "
        "then analyze it with analyze_vision and trust the returned report as if "
        "you saw it yourself. Never finish a UI fix on a guess. If a tool returns "
        "status=environment_incomplete, relay the guide to the user, wait, then retry.\n\n"
        "Screen capture: whenever you need a screenshot — a full monitor, a specific "
        "app window, or a selected region — ALWAYS use take_screenshot (with "
        "list_monitors / list_windows to pick a target). Do NOT write your own "
        "one-off capture script (screencapture, mss, PIL.ImageGrab, PowerShell, "
        "etc.); this server already handles every capture mode cross-platform, with "
        "the user's permissions and the configured save folder. take_screenshot can "
        "be used on its own — you are free to just capture without analyzing.\n\n"
        "If you can truly see images yourself (you are a vision-capable model), you "
        "may set self_analyze=true on analyze_vision/capture_and_analyze instead of "
        "using an external backend. This runs a capability check: a small image "
        "showing a verification code comes back, which you must read and echo via "
        "vision_check before your screenshot is returned for analysis. Only set "
        "self_analyze=true if you "
        "can actually see images — if you cannot read the code, do not guess it and "
        "do not invent a description (fabricating vision gains nothing); fall back to "
        "self_analyze=false to route the image to the configured vision backend."
    ),
)


def _not_implemented(feature: str, milestone: str) -> dict[str, Any]:
    return {
        "status": "not_implemented",
        "feature": feature,
        "message": f"'{feature}' is provided in milestone {milestone}.",
    }


# --------------------------------------------------------------------------- #
# Environment (plan §5.5, §3.3.3)
# --------------------------------------------------------------------------- #
@mcp.tool
def check_environment() -> dict[str, Any]:
    """Check the runtime/packages/permissions/credentials/settings and return a guide for any gaps."""
    status = EnvironmentChecker().check_full()
    if status.ok:
        return {"status": "ok", "message": "Environment is fully configured."}
    return status.to_guide()


# --------------------------------------------------------------------------- #
# Capture (plan §5.1, §5.2) — implemented in M2/M3
# --------------------------------------------------------------------------- #
@mcp.tool
def list_monitors() -> dict[str, Any]:
    """Return the list of monitors available for capture."""
    env = EnvironmentChecker().check_for_capture()
    if not env.ok:
        return env.to_guide()
    from ..capture import get_capture_backend  # noqa: PLC0415

    backend = get_capture_backend()
    if backend is None:
        return _not_implemented("list_monitors", "M2")
    return {"status": "ok", "monitors": [m.model_dump() for m in backend.list_monitors()]}


@mcp.tool
def list_windows() -> dict[str, Any]:
    """Return open windows available for capture (app name / title / id)."""
    env = EnvironmentChecker().check_for_capture()
    if not env.ok:
        return env.to_guide()
    from ..capture import get_capture_backend  # noqa: PLC0415

    backend = get_capture_backend()
    if backend is None:
        return _not_implemented("list_windows", "M3")
    return {"status": "ok", "windows": [w.model_dump() for w in backend.list_windows()]}


@mcp.tool
def take_screenshot(
    target: str = "monitor",
    monitor_index: int = 0,
    window_id: int | None = None,
    app_name: str | None = None,
    title_contains: str | None = None,
    x: int | None = None,
    y: int | None = None,
    w: int | None = None,
    h: int | None = None,
) -> dict[str, Any]:
    """Capture the screen and save it to the target folder, returning the saved path.

    Use this for ANY screenshot need — do not write your own capture script
    (screencapture / mss / PIL.ImageGrab / PowerShell); this tool covers every
    capture mode cross-platform. It can be used standalone (just capture, no
    analysis required).

    target:
      - 'monitor'            : full screen of a monitor (monitor_index; see list_monitors)
      - 'window'             : a specific app window (window_id, or app_name/title_contains
                               selector; see list_windows)
      - 'region'             : coordinate region (x, y, w, h; pixels from the primary display's top-left)
      - 'region_interactive' : the user drag-selects a rectangle (requires user interaction)

    Small regions are sent as-is for analysis; large ones are auto-downscaled (§7.5).
    """
    from ..core.capture_service import perform_capture  # noqa: PLC0415

    # Clipboard auto-copy is a user-initiated convenience (tray capture / recent).
    # An LLM tool call is not the user acting, so never copy here regardless of
    # the clipboard_auto setting.
    return perform_capture(
        target,
        monitor_index=monitor_index,
        window_id=window_id,
        app_name=app_name,
        title_contains=title_contains,
        x=x, y=y, w=w, h=h,
        copy_clipboard=False,
    )


# --------------------------------------------------------------------------- #
# Vision (plan §5.3, §5.4) — implemented in M1
# --------------------------------------------------------------------------- #
@mcp.tool(output_schema=None)
def analyze_vision(
    image_path: str,
    prompt: str = (
        "Find overlapping/broken parts, misalignment, and clipped/occluded elements "
        "in this UI, and explain them with the likely CSS/style areas to fix."
    ),
    backend: str | None = None,
    self_analyze: bool = False,
    vision_check: str | None = None,
) -> Any:
    """Analyze an image (path + prompt) with the vision backend and return a structured report.

    self_analyze=true: only for models that can actually see images. This does NOT
    immediately analyze — it first returns a small image showing a verification
    code (a capability check). Read that code and call again with vision_check set
    to it; your screenshot is returned for analysis only if the code matches. If you
    cannot read the code you are not vision-capable: do not guess it (fabricating
    vision gains nothing) — call again with self_analyze=false to use the backend.
    """
    target = Path(image_path).expanduser()
    if not target.exists():
        return {
            "status": "error",
            "code": "image_not_found",
            "message": (
                f"Image not found: {target}. It may have been deleted or moved, or "
                "the target folder changed. Re-capture with take_screenshot and use "
                "the returned path."
            ),
        }
    if self_analyze:
        from .vision_service import build_self_analysis  # noqa: PLC0415

        return build_self_analysis(
            target, prompt, vision_check=vision_check, backend_id=backend
        )
    env = EnvironmentChecker().check_for_vision(backend)
    if not env.ok:
        return env.to_guide()
    from .vision_service import run_analysis  # noqa: PLC0415

    return run_analysis(target, prompt, backend)


@mcp.tool(output_schema=None)
def capture_and_analyze(
    target: str = "monitor",
    monitor_index: int = 0,
    window_id: int | None = None,
    app_name: str | None = None,
    title_contains: str | None = None,
    x: int | None = None,
    y: int | None = None,
    w: int | None = None,
    h: int | None = None,
    prompt: str | None = None,
    backend: str | None = None,
    self_analyze: bool = False,
) -> Any:
    """Convenience chain: capture then analyze (plan §5.4). `target` matches take_screenshot.

    self_analyze=true: if you are a vision-capable model, capture then get the
    image back to analyze yourself instead of routing it to an external backend.
    """
    shot = take_screenshot(
        target=target, monitor_index=monitor_index, window_id=window_id,
        app_name=app_name, title_contains=title_contains, x=x, y=y, w=w, h=h
    )
    if shot.get("status") != "ok":
        return shot
    kwargs: dict[str, Any] = {
        "image_path": shot["path"], "backend": backend, "self_analyze": self_analyze,
    }
    if prompt is not None:
        kwargs["prompt"] = prompt
    return analyze_vision(**kwargs)


# --------------------------------------------------------------------------- #
# Settings (plan §5.6)
# --------------------------------------------------------------------------- #
@mcp.tool
def get_config() -> dict[str, Any]:
    """Return the current settings (target folder, providers, default provider). Never includes API keys."""
    config = cfg.load_config()
    return {
        "status": "ok",
        "target_folder": config.target_folder,
        "default_provider_id": config.default_provider_id,
        "last_used_provider_id": config.last_used_provider_id,
        "providers": [
            {"id": p.id, "type": p.type, "label": p.label, "model": p.model, "is_local": p.is_local}
            for p in config.providers
        ],
    }


@mcp.tool
def set_target_folder(path: str) -> dict[str, Any]:
    """Set the target folder where captures are saved (shares the tray app's config file)."""
    folder = Path(path).expanduser()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"status": "error", "message": f"Cannot create folder: {exc}"}
    config = cfg.load_config()
    config.target_folder = str(folder)
    cfg.save_config(config)
    return {"status": "ok", "target_folder": str(folder)}


def get_app() -> FastMCP:
    return mcp
