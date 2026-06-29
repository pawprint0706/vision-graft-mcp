"""Windows capture backend — mss + Win32 (plan §6.3).

M6.1: monitor / region / window capture + window/monitor enumeration.
M6.2: interactive drag-select via a tkinter overlay.

Strategy (docs/windows-port-plan.md §2 작업 1): capture what is *drawn on screen*
by grabbing the window's on-screen rect with ``mss`` — DWM has already composited
the frame, so hardware-accelerated windows (e.g. Chrome with GPU rendering) come
out correctly, unlike ``PrintWindow`` which often yields a black frame. The target
window is brought to the front best-effort first; if Windows' focus-stealing
prevention blocks that, we capture anyway and accept that an overlapping window may
be included.

DirectX exclusive-fullscreen apps (games) are out of scope; the robust
``Windows.Graphics.Capture`` path is deferred to M6.6.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from ..core.errors import CaptureError
from ..core.models import CaptureResult, MonitorInfo, WindowBounds, WindowInfo


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def _safe_name(name: str) -> str:
    """Normalize an app name to a filesystem-safe token (plan §4.2.2)."""
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in name).strip("_")
    return cleaned or "window"


def _set_dpi_awareness() -> None:
    """Make the process per-monitor DPI aware (plan §3.1.3, §6.3).

    Without this, ``GetWindowRect`` / ``mss`` coordinates are reported in
    DPI-virtualized (scaled) pixels and capture regions land in the wrong place
    on high-DPI or mixed-DPI multi-monitor setups. Idempotent and best-effort:
    each call after the first (or once the manifest already set awareness) fails
    harmlessly and is ignored.
    """
    import ctypes  # noqa: PLC0415

    # PER_MONITOR_AWARE_V2 (Win10 1703+) — best fidelity.
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    # PROCESS_PER_MONITOR_DPI_AWARE (Win8.1+).
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    # System-DPI aware (Vista+) — last resort.
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def _dpi_scale_for_point(x: int, y: int) -> float:
    """Backing scale (e.g. 1.0, 1.5, 2.0) of the monitor containing (x, y)."""
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    try:
        MONITOR_DEFAULTTONEAREST = 2
        hmon = ctypes.windll.user32.MonitorFromPoint(
            wintypes.POINT(x, y), MONITOR_DEFAULTTONEAREST
        )
        dpi_x = ctypes.c_uint()
        dpi_y = ctypes.c_uint()
        # MDT_EFFECTIVE_DPI = 0
        if ctypes.windll.shcore.GetDpiForMonitor(
            hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
        ) == 0:
            return dpi_x.value / 96.0
    except (AttributeError, OSError):
        pass
    return 1.0


def _save_png(grab, path: Path) -> tuple[int, int]:
    """Write an mss screenshot to PNG; returns (width, height)."""
    import mss.tools  # noqa: PLC0415

    mss.tools.to_png(grab.rgb, grab.size, output=str(path))
    return int(grab.width), int(grab.height)


def _is_blank(grab) -> bool:
    """True if a grab is essentially solid black — the signature of a window that
    refuses capture (DRM via SetWindowDisplayAffinity/WDA_EXCLUDEFROMCAPTURE,
    DirectX exclusive-fullscreen, etc.). Samples ~2000 pixels for speed."""
    rgb = grab.rgb
    n = len(rgb)
    if n < 3:
        return True
    stride = max(3, (n // 3 // 2000) * 3)
    total = samples = 0
    for i in range(0, n - 2, stride):
        total += rgb[i] + rgb[i + 1] + rgb[i + 2]
        samples += 1
    return (total / (samples * 3)) < 6 if samples else True  # ~0/255 brightness


# --------------------------------------------------------------------------- #
# Backend
# --------------------------------------------------------------------------- #
class WindowsCaptureBackend:
    """mss + Win32 capture backend (plan §6.3)."""

    def __init__(self) -> None:
        _set_dpi_awareness()

    # -- enumeration ------------------------------------------------------- #
    def list_monitors(self) -> list[MonitorInfo]:
        import mss  # noqa: PLC0415

        out: list[MonitorInfo] = []
        with mss.mss() as sct:
            # sct.monitors[0] is the union of all monitors; [1:] are individual.
            for idx, mon in enumerate(sct.monitors[1:]):
                left, top = int(mon["left"]), int(mon["top"])
                out.append(
                    MonitorInfo(
                        index=idx,
                        width=int(mon["width"]),
                        height=int(mon["height"]),
                        dpi_scale=_dpi_scale_for_point(left, top),
                        # The primary monitor's top-left is the virtual origin.
                        primary=(left == 0 and top == 0),
                    )
                )
        return out

    def list_windows(self) -> list[WindowInfo]:
        import win32con  # noqa: PLC0415
        import win32gui  # noqa: PLC0415
        import win32process  # noqa: PLC0415

        out: list[WindowInfo] = []

        def _collect(hwnd: int, _ctx) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            # Tool windows (palettes, tooltips) are not user-facing app windows.
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return True
            if _is_cloaked(hwnd):  # hidden UWP / other-virtual-desktop windows
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return True
            # Minimized windows are kept: capture_window restores them first, so
            # they are still selectable. They report an off-screen sentinel rect,
            # so only size-filter the genuinely zero-area non-minimized ones.
            iconic = win32gui.IsIconic(hwnd)
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            w, h = right - left, bottom - top
            if not iconic and (w <= 1 or h <= 1):
                return True
            pid: int | None = None
            app_name = ""
            try:
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                app_name = _process_name(pid)
            except Exception:  # noqa: BLE001 — best-effort attribution
                pass
            out.append(
                WindowInfo(
                    window_id=int(hwnd),
                    app_name=app_name,
                    title=title,
                    pid=pid,
                    bounds=None if iconic else WindowBounds(x=left, y=top, w=w, h=h),
                    on_screen=not iconic,
                )
            )
            return True

        win32gui.EnumWindows(_collect, None)
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

    # -- capture ----------------------------------------------------------- #
    def capture_monitor(self, index: int, dest: Path) -> CaptureResult:
        import mss  # noqa: PLC0415

        with mss.mss() as sct:
            monitors = sct.monitors[1:]
            if index < 0 or index >= len(monitors):
                raise CaptureError(
                    f"Monitor index out of range: {index} (0..{len(monitors) - 1})"
                )
            grab = sct.grab(monitors[index])
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / f"monitor{index}_{_timestamp()}.png"
            width, height = _save_png(grab, path)
        return CaptureResult(path=str(path), width=width, height=height, source=f"monitor{index}")

    def capture_window(self, window_id: int, dest: Path) -> CaptureResult:
        import mss  # noqa: PLC0415
        import win32gui  # noqa: PLC0415

        hwnd = int(window_id)
        if not win32gui.IsWindow(hwnd):
            raise CaptureError(f"Window not found: window_id={window_id}")

        _bring_to_front(hwnd)
        app_name = self._app_name_for(hwnd)
        left, top, right, bottom = _window_bounds(hwnd)
        w, h = right - left, bottom - top
        dest.mkdir(parents=True, exist_ok=True)

        if w > 0 and h > 0:
            with mss.mss() as sct:
                grab = sct.grab({"left": left, "top": top, "width": w, "height": h})
                if not _is_blank(grab):
                    path = dest / f"{_safe_name(app_name)}_{_timestamp()}.png"
                    width, height = _save_png(grab, path)
                    return CaptureResult(path=str(path), width=width, height=height,
                                         source=app_name)

        # The window refused capture (blank frame) or has no usable rect. Fall
        # back to the whole monitor it sits on, so the user still gets the view.
        index = _monitor_index_for_window(hwnd)
        res = self.capture_monitor(index, dest)
        return CaptureResult(
            path=res.path, width=res.width, height=res.height,
            source=f"{app_name} (window capture unavailable — monitor{index} fallback)",
        )

    def capture_region(self, x: int, y: int, w: int, h: int, dest: Path) -> CaptureResult:
        """Capture a rectangle in virtual-desktop pixels (primary top-left = origin)."""
        import mss  # noqa: PLC0415

        if w <= 0 or h <= 0:
            raise CaptureError(f"Invalid region size: {w}x{h}")
        with mss.mss() as sct:
            grab = sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / f"region_{_timestamp()}.png"
            width, height = _save_png(grab, path)
        return CaptureResult(path=str(path), width=width, height=height, source="region")

    def capture_region_interactive(self, dest: Path) -> CaptureResult | None:
        """Drag-select a rectangle via a fullscreen overlay (plan §6.5).

        Returns None if the user cancels (Esc or an empty selection). Must run on
        the main thread (Tk requirement) — the tray invokes it that way.
        """
        selection = _interactive_select()
        if selection is None:
            return None
        x, y, w, h = selection
        if w <= 0 or h <= 0:
            return None
        return self.capture_region(x, y, w, h, dest)

    def check_permission(self) -> bool:
        """Windows has no screen-recording permission gate (plan §3.1.3)."""
        return True

    # -- internals --------------------------------------------------------- #
    def _app_name_for(self, hwnd: int) -> str:
        import win32process  # noqa: PLC0415

        try:
            _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            name = _process_name(pid)
            if name:
                return name
        except Exception:  # noqa: BLE001
            pass
        return "window"


# --------------------------------------------------------------------------- #
# Win32 free functions
# --------------------------------------------------------------------------- #
def _is_cloaked(hwnd: int) -> bool:
    """True for DWM-cloaked windows (hidden UWP / other virtual desktops)."""
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    DWMWA_CLOAKED = 14
    value = ctypes.c_int(0)
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_CLOAKED,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except (AttributeError, OSError):
        return False
    return value.value != 0


def _window_bounds(hwnd: int) -> tuple[int, int, int, int]:
    """The window's true on-screen rect, excluding the invisible DWM shadow.

    Falls back to GetWindowRect (which includes the shadow border) if the DWM
    attribute query fails.
    """
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    rect = wintypes.RECT()
    try:
        res = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if res == 0:
            return rect.left, rect.top, rect.right, rect.bottom
    except (AttributeError, OSError):
        pass
    import win32gui  # noqa: PLC0415

    return win32gui.GetWindowRect(hwnd)


def _monitor_index_for_window(hwnd: int) -> int:
    """0-based index (matching list_monitors / capture_monitor) of the monitor the
    window sits on. Falls back to 0 (primary) if it can't be determined."""
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    try:
        MONITOR_DEFAULTTONEAREST = 2
        hmon = ctypes.windll.user32.MonitorFromWindow(
            wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST
        )
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            return 0
        left, top = info.rcMonitor.left, info.rcMonitor.top
    except (AttributeError, OSError):
        return 0

    import mss  # noqa: PLC0415

    with mss.mss() as sct:
        monitors = sct.monitors[1:]
        for idx, mon in enumerate(monitors):  # exact top-left match
            if int(mon["left"]) == left and int(mon["top"]) == top:
                return idx
        for idx, mon in enumerate(monitors):  # else: contains the top-left point
            if (mon["left"] <= left < mon["left"] + mon["width"]
                    and mon["top"] <= top < mon["top"] + mon["height"]):
                return idx
    return 0


def _bring_to_front(hwnd: int) -> None:
    """Best-effort raise the target window so it is fully drawn before capture.

    Windows' focus-stealing prevention may block SetForegroundWindow when another
    process owns the foreground; we do NOT fight it with AttachThreadInput / fake
    ALT hacks (docs/windows-port-plan.md §2). If it fails we capture anyway and
    accept a possibly-overlapped frame.
    """
    import win32con  # noqa: PLC0415
    import win32gui  # noqa: PLC0415

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.BringWindowToTop(hwnd)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:  # noqa: BLE001 — focus-stealing prevention; ignore
            pass
        time.sleep(0.12)  # let DWM finish compositing the raised window
    except Exception:  # noqa: BLE001 — raising is optional; never block capture
        pass


def _process_name(pid: int) -> str:
    """Executable stem (e.g. 'chrome') for a process id, or '' on failure.

    Uses kernel32.QueryFullProcessImageNameW via ctypes — it resolves with only
    PROCESS_QUERY_LIMITED_INFORMATION (works for elevated/protected processes)
    and is present across pywin32 builds, unlike win32process.QueryFullProcessImageName.
    """
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).stem
    finally:
        kernel32.CloseHandle(handle)
    return ""


# --------------------------------------------------------------------------- #
# Interactive selection overlay
# --------------------------------------------------------------------------- #
def _virtual_desktop() -> tuple[int, int, int, int]:
    """(left, top, width, height) of the union of all monitors."""
    import ctypes  # noqa: PLC0415

    user32 = ctypes.windll.user32
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def _interactive_select() -> tuple[int, int, int, int] | None:
    """Fullscreen translucent overlay; returns (x, y, w, h) in virtual-desktop
    pixels, or None if cancelled.

    Known caveat (refine in a later milestone): Tk is not fully per-monitor DPI
    aware, so on mixed-DPI setups the selected rect can be off by the scale
    factor. Acceptable for the M6.2 MVP.
    """
    import tkinter as tk  # noqa: PLC0415

    vx, vy, vw, vh = _virtual_desktop()
    state: dict[str, object] = {"start": None, "rect": None}

    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{vw}x{vh}+{vx}+{vy}")
    root.attributes("-alpha", 0.3)
    root.attributes("-topmost", True)
    root.configure(bg="black")
    canvas = tk.Canvas(root, bg="black", highlightthickness=0, cursor="cross")
    canvas.pack(fill="both", expand=True)
    box = {"id": None}

    def on_press(event) -> None:
        state["start"] = (event.x_root, event.y_root)

    def on_move(event) -> None:
        if state["start"] is None:
            return
        sx, sy = state["start"]  # type: ignore[misc]
        if box["id"] is not None:
            canvas.delete(box["id"])
        box["id"] = canvas.create_rectangle(
            sx - vx, sy - vy, event.x_root - vx, event.y_root - vy,
            outline="#4aa3ff", width=2,
        )

    def on_release(event) -> None:
        if state["start"] is not None:
            sx, sy = state["start"]  # type: ignore[misc]
            x0, x1 = sorted((sx, event.x_root))
            y0, y1 = sorted((sy, event.y_root))
            state["rect"] = (x0, y0, x1 - x0, y1 - y0)
        root.destroy()

    def on_cancel(_event) -> None:
        state["rect"] = None
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_move)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_cancel)
    root.focus_force()
    root.mainloop()

    return state["rect"]  # type: ignore[return-value]
