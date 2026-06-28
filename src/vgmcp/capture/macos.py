"""macOS capture backend — ScreenCaptureKit (plan §2.4.3, §6.2).

M2: monitor capture + list_monitors. M3 adds window capture/enumeration.

Why ScreenCaptureKit: CGWindowListCreateImage is obsoleted in macOS 15.0 and
deprecated capture APIs escalate Sequoia's permission nag (plan §9.1).
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..core.errors import CaptureError
from ..core.models import CaptureResult, MonitorInfo, WindowInfo

_SYNC_TIMEOUT = 10.0


def _run_sync(starter: Callable[[Callable], None], timeout: float = _SYNC_TIMEOUT):
    """Drive an SCK completion-handler API synchronously.

    `starter` receives a handler(result, error) and kicks off the async call.
    Returns the result or raises CaptureError.
    """
    done = threading.Event()
    box: dict[str, object] = {}

    def handler(result, error):
        box["result"] = result
        box["error"] = error
        done.set()

    starter(handler)
    if not done.wait(timeout):
        raise CaptureError("ScreenCaptureKit 호출이 시간 내에 응답하지 않았습니다.")
    if box.get("error") is not None:
        raise CaptureError(f"ScreenCaptureKit 오류: {box['error']}")
    return box.get("result")


def _shareable_content():
    import ScreenCaptureKit as SCK  # noqa: PLC0415

    return _run_sync(
        SCK.SCShareableContent.getShareableContentWithCompletionHandler_
    )


def _scale_by_display_id() -> dict[int, float]:
    """Map CGDirectDisplayID -> backingScaleFactor (retina detection)."""
    from AppKit import NSScreen  # noqa: PLC0415

    out: dict[int, float] = {}
    for screen in NSScreen.screens():
        desc = screen.deviceDescription()
        num = desc.get("NSScreenNumber")
        if num is not None:
            out[int(num)] = float(screen.backingScaleFactor())
    return out


def _cgimage_to_png(cgimage, path: Path) -> tuple[int, int]:
    import Quartz  # noqa: PLC0415
    from Foundation import NSURL  # noqa: PLC0415

    width = int(Quartz.CGImageGetWidth(cgimage))
    height = int(Quartz.CGImageGetHeight(cgimage))
    url = NSURL.fileURLWithPath_(str(path))
    dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    if dest is None:
        raise CaptureError(f"이미지 대상 생성 실패: {path}")
    Quartz.CGImageDestinationAddImage(dest, cgimage, None)
    if not Quartz.CGImageDestinationFinalize(dest):
        raise CaptureError(f"PNG 저장 실패: {path}")
    return width, height


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


class MacOSCaptureBackend:
    """ScreenCaptureKit-based capture (plan §6.2)."""

    def _displays(self):
        content = _shareable_content()
        if content is None:
            raise CaptureError("공유 가능한 화면 콘텐츠를 가져오지 못했습니다(권한 확인).")
        return list(content.displays())

    def list_monitors(self) -> list[MonitorInfo]:
        import Quartz  # noqa: PLC0415

        main_id = int(Quartz.CGMainDisplayID())
        scales = _scale_by_display_id()
        monitors: list[MonitorInfo] = []
        for idx, disp in enumerate(self._displays()):
            disp_id = int(disp.displayID())
            scale = scales.get(disp_id, 1.0)
            monitors.append(
                MonitorInfo(
                    index=idx,
                    width=int(disp.width() * scale),
                    height=int(disp.height() * scale),
                    dpi_scale=scale,
                    primary=(disp_id == main_id),
                )
            )
        return monitors

    def list_windows(self) -> list[WindowInfo]:  # noqa: D102 — M3
        raise NotImplementedError("list_windows lands in M3")

    def capture_monitor(self, index: int, dest: Path) -> CaptureResult:
        import Quartz  # noqa: PLC0415, F401 — must load CGImage metadata before capture
        import ScreenCaptureKit as SCK  # noqa: PLC0415

        displays = self._displays()
        if index < 0 or index >= len(displays):
            raise CaptureError(f"모니터 인덱스 범위를 벗어났습니다: {index} (0..{len(displays) - 1})")
        disp = displays[index]
        scales = _scale_by_display_id()
        scale = scales.get(int(disp.displayID()), 1.0)

        content_filter = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(disp, [])
        config = SCK.SCStreamConfiguration.alloc().init()
        # Capture at full pixel resolution (retina-aware).
        config.setWidth_(int(disp.width() * scale))
        config.setHeight_(int(disp.height() * scale))

        cgimage = _run_sync(
            lambda h: SCK.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(
                content_filter, config, h
            )
        )
        if cgimage is None:
            raise CaptureError("캡처 결과 이미지가 비어 있습니다(권한/디스플레이 확인).")

        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"monitor{index}_{_timestamp()}.png"
        width, height = _cgimage_to_png(cgimage, path)
        return CaptureResult(path=str(path), width=width, height=height, source=f"monitor{index}")

    def capture_window(self, window_id: int, dest: Path) -> CaptureResult:  # noqa: D102 — M3
        raise NotImplementedError("capture_window lands in M3")

    def check_permission(self) -> bool:
        """Probe Screen Recording permission via SCShareableContent (plan §3.2.2)."""
        try:
            content = _shareable_content()
        except CaptureError:
            return False
        if content is None:
            return False
        displays = content.displays()
        return displays is not None and len(displays) > 0
