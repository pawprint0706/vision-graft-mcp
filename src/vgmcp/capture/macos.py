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


_app_initialized = False


def _ensure_app() -> None:
    """Establish the window-server connection (plan §2.4.2).

    Per-window ScreenCaptureKit filters (SCContentFilter desktopIndependentWindow)
    require an initialized CoreGraphics/window-server connection, which a bare
    CLI process lacks (raises CGS_REQUIRE_INIT). NSApplication.sharedApplication()
    establishes it and is idempotent. The tray app's rumps loop already does this.
    """
    global _app_initialized
    if _app_initialized:
        return
    import AppKit  # noqa: PLC0415

    AppKit.NSApplication.sharedApplication()
    _app_initialized = True


def _safe_name(name: str) -> str:
    """Normalize an app name to a filesystem-safe token (plan §4.2.2)."""
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in name).strip("_")
    return cleaned or "window"


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

    def _windows(self):
        content = _shareable_content()
        if content is None:
            raise CaptureError("공유 가능한 화면 콘텐츠를 가져오지 못했습니다(권한 확인).")
        return list(content.windows())

    def list_windows(self) -> list[WindowInfo]:
        _ensure_app()
        from ..core.models import WindowBounds  # noqa: PLC0415

        out: list[WindowInfo] = []
        for win in self._windows():
            if not win.isOnScreen():
                continue
            app = win.owningApplication()
            app_name = app.applicationName() if app is not None else ""
            if not app_name:
                continue
            frame = win.frame()
            w = int(frame.size.width)
            h = int(frame.size.height)
            if w <= 1 or h <= 1:
                continue
            out.append(
                WindowInfo(
                    window_id=int(win.windowID()),
                    app_name=str(app_name),
                    title=str(win.title() or ""),
                    pid=int(app.processID()) if app is not None else None,
                    bounds=WindowBounds(x=int(frame.origin.x), y=int(frame.origin.y), w=w, h=h),
                    on_screen=True,
                )
            )
        out.sort(key=lambda wi: (wi.app_name.lower(), wi.title.lower()))
        return out

    def find_window(self, app_name: str | None, title_contains: str | None) -> int | None:
        """Resolve a window_id from a human-friendly selector (plan §6.4)."""
        for wi in self.list_windows():
            if app_name and app_name.lower() not in wi.app_name.lower():
                continue
            if title_contains and title_contains.lower() not in wi.title.lower():
                continue
            return wi.window_id
        return None

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

    def capture_window(self, window_id: int, dest: Path) -> CaptureResult:
        import Quartz  # noqa: PLC0415, F401 — load CGImage metadata before capture
        import ScreenCaptureKit as SCK  # noqa: PLC0415

        _ensure_app()
        scwin = next((w for w in self._windows() if int(w.windowID()) == window_id), None)
        if scwin is None:
            raise CaptureError(f"윈도우를 찾을 수 없습니다: window_id={window_id}")

        content_filter = SCK.SCContentFilter.alloc().initWithDesktopIndependentWindow_(scwin)
        # contentRect (points) * pointPixelScale -> full-resolution pixel size.
        scale = float(content_filter.pointPixelScale())
        rect = content_filter.contentRect()
        config = SCK.SCStreamConfiguration.alloc().init()
        config.setWidth_(max(1, int(rect.size.width * scale)))
        config.setHeight_(max(1, int(rect.size.height * scale)))

        cgimage = _run_sync(
            lambda h: SCK.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(
                content_filter, config, h
            )
        )
        if cgimage is None:
            raise CaptureError("윈도우 캡처 결과 이미지가 비어 있습니다.")

        app = scwin.owningApplication()
        app_name = app.applicationName() if app is not None else "window"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{_safe_name(app_name)}_{_timestamp()}.png"
        width, height = _cgimage_to_png(cgimage, path)
        return CaptureResult(path=str(path), width=width, height=height, source=str(app_name))

    def capture_region(self, x: int, y: int, w: int, h: int, dest: Path) -> CaptureResult:
        """Programmatic region capture: full primary capture cropped to the rect.

        Coordinates are pixels with the primary display's top-left as origin.
        """
        from PIL import Image  # noqa: PLC0415

        if w <= 0 or h <= 0:
            raise CaptureError(f"영역 크기가 유효하지 않습니다: {w}x{h}")
        full = self.capture_monitor(0, dest)
        full_path = Path(full.path)
        try:
            with Image.open(full_path) as im:
                im.load()
                left = max(0, x)
                top = max(0, y)
                right = min(im.width, x + w)
                bottom = min(im.height, y + h)
                if right <= left or bottom <= top:
                    raise CaptureError("요청한 영역이 화면 범위를 벗어났습니다.")
                cropped = im.crop((left, top, right, bottom))
                path = dest / f"region_{_timestamp()}.png"
                cropped.save(path, format="PNG")
                out_w, out_h = cropped.size
        finally:
            # The intermediate full-screen capture is not the user's target.
            full_path.unlink(missing_ok=True)
        return CaptureResult(path=str(path), width=out_w, height=out_h, source="region")

    def capture_region_interactive(self, dest: Path) -> CaptureResult | None:
        """Interactive drag-select via the native `screencapture -i` (plan §6.5).

        `screencapture` is Apple's supported system utility (not the obsoleted
        CGWindowListCreateImage C API), so it gives a robust crosshair selection.
        Returns None if the user cancels (Esc → no file written).
        """
        import subprocess  # noqa: PLC0415

        from PIL import Image  # noqa: PLC0415

        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"region_{_timestamp()}.png"
        # -i interactive selection, -x no capture sound.
        try:
            subprocess.run(
                ["/usr/sbin/screencapture", "-i", "-x", str(path)],
                check=True,
                timeout=120,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise CaptureError(f"screencapture 실행 실패: {exc}") from exc
        except subprocess.TimeoutExpired:
            return None
        if not path.exists():
            return None  # user cancelled the selection
        with Image.open(path) as im:
            width, height = im.size
        return CaptureResult(path=str(path), width=width, height=height, source="region")

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
