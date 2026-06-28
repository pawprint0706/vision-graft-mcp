"""Shared capture orchestration (plan §2.3).

Both the MCP `take_screenshot` tool and the tray menu call this, so the lazy
environment check, recent-image tracking, and optional clipboard prompt happen
in exactly one place. Returns a tool-shaped result dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import clipboard
from . import config as cfg
from .environment import EnvironmentChecker
from .errors import CaptureError
from .mainthread import run_on_main


def perform_capture(
    target: str = "monitor",
    *,
    monitor_index: int = 0,
    window_id: int | None = None,
    app_name: str | None = None,
    title_contains: str | None = None,
    x: int | None = None,
    y: int | None = None,
    w: int | None = None,
    h: int | None = None,
    copy_clipboard: bool | None = None,
) -> dict[str, Any]:
    from ..capture import get_capture_backend  # noqa: PLC0415

    env = EnvironmentChecker().check_for_capture()
    if not env.ok:
        return env.to_guide()
    backend = get_capture_backend()
    if backend is None:
        return {"status": "not_implemented", "feature": "capture",
                "message": "No capture backend for this platform yet."}

    config = cfg.load_config()
    dest = Path(config.target_folder)

    def _do_capture():
        wid = window_id
        try:
            if target == "window":
                if wid is None and (app_name or title_contains):
                    wid = backend.find_window(app_name, title_contains)
                    if wid is None:
                        return {"status": "error",
                                "message": "No window matched the selector. Check list_windows."}
                if wid is None:
                    return {"status": "error",
                            "message": "target='window' needs window_id or app_name/title_contains."}
                return backend.capture_window(wid, dest)
            if target == "region":
                if None in (x, y, w, h):
                    return {"status": "error", "message": "target='region' needs all of x, y, w, h."}
                return backend.capture_region(x, y, w, h, dest)
            if target == "region_interactive":
                res = backend.capture_region_interactive(dest)
                if res is None:
                    return {"status": "cancelled", "message": "Region selection was cancelled."}
                return res
            return backend.capture_monitor(monitor_index, dest)
        except NotImplementedError:
            return {"status": "not_implemented", "feature": f"capture:{target}"}
        except CaptureError as exc:
            return {"status": "error", "message": str(exc)}

    # ScreenCaptureKit/AppKit must run on the main thread (plan §2.4.2).
    outcome = run_on_main(_do_capture)
    if isinstance(outcome, dict):
        return outcome  # error / cancelled / not_implemented
    return _post_capture(outcome, config, copy_clipboard)


def register_image(path: str, *, copy_clipboard: bool | None = None) -> dict[str, Any]:
    """Register an externally-provided image (e.g. 'open image file', plan §4.2.3).

    If `copy_original` is set, the file is copied into the target folder (so it's
    managed alongside captures and survives the original being moved/deleted);
    otherwise the original path is referenced as-is.
    """
    from .models import CaptureResult  # noqa: PLC0415

    p = Path(path)
    if not p.exists():
        return {"status": "error", "message": f"File does not exist: {path}"}
    try:
        from PIL import Image  # noqa: PLC0415

        with Image.open(p) as im:
            width, height = im.size
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": f"Cannot open image: {exc}"}

    config = cfg.load_config()
    dest_path = p
    target = Path(config.target_folder)
    if config.copy_original and p.resolve().parent != target.resolve():
        import shutil  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415

        target.mkdir(parents=True, exist_ok=True)
        stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in p.stem).strip("_") or "image"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        dest_path = target / f"opened_{stem}_{ts}{p.suffix.lower()}"
        try:
            shutil.copy2(p, dest_path)
        except OSError as exc:
            return {"status": "error", "message": f"Failed to copy into target folder: {exc}"}

    result = CaptureResult(path=str(dest_path), width=width, height=height, source="file")
    return _post_capture(result, config, copy_clipboard)


def _post_capture(result, config, copy_clipboard: bool | None) -> dict[str, Any]:
    """Record recent + optional clipboard copy, then persist (plan §4.1, §8.2)."""
    config.add_recent(result.path)
    out = result.model_dump()
    do_copy = config.clipboard_auto if copy_clipboard is None else copy_clipboard
    if do_copy:
        ok, _text = clipboard.copy_prompt(
            result.path, config.clipboard_template, capture_source=result.source
        )
        out["clipboard_copied"] = ok
    cfg.save_config(config)
    return out
