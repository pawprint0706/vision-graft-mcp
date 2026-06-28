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
                "message": "이 플랫폼의 캡처 백엔드가 아직 없습니다."}

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
                                "message": "셀렉터에 맞는 윈도우를 찾지 못했습니다. list_windows로 확인하십시오."}
                if wid is None:
                    return {"status": "error",
                            "message": "target='window'에는 window_id 또는 app_name/title_contains가 필요합니다."}
                return backend.capture_window(wid, dest)
            if target == "region":
                if None in (x, y, w, h):
                    return {"status": "error", "message": "target='region'에는 x, y, w, h가 모두 필요합니다."}
                return backend.capture_region(x, y, w, h, dest)
            if target == "region_interactive":
                res = backend.capture_region_interactive(dest)
                if res is None:
                    return {"status": "cancelled", "message": "사용자가 영역 선택을 취소했습니다."}
                return res
            return backend.capture_monitor(monitor_index, dest)
        except NotImplementedError:
            return {"status": "not_implemented", "feature": f"capture:{target}"}

    # ScreenCaptureKit/AppKit must run on the main thread (plan §2.4.2).
    outcome = run_on_main(_do_capture)
    if isinstance(outcome, dict):
        return outcome  # error / cancelled / not_implemented
    return _post_capture(outcome, config, copy_clipboard)


def register_image(path: str, *, copy_clipboard: bool | None = None) -> dict[str, Any]:
    """Register an externally-provided image (e.g. 'open image file', plan §4.2.3)."""
    from .models import CaptureResult  # noqa: PLC0415

    p = Path(path)
    if not p.exists():
        return {"status": "error", "message": f"파일이 존재하지 않습니다: {path}"}
    try:
        from PIL import Image  # noqa: PLC0415

        with Image.open(p) as im:
            width, height = im.size
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": f"이미지를 열 수 없습니다: {exc}"}
    result = CaptureResult(path=str(p), width=width, height=height, source="file")
    return _post_capture(result, cfg.load_config(), copy_clipboard)


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
