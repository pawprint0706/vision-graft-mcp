"""Windows system-tray app (plan §4, docs/windows-port-plan.md §2 작업 2).

Functional peer of tray/macos.py, built on pystray (tray icon + menu) and
tkinter (dialogs) instead of rumps/AppKit. Runs the resident HTTP host on a
background thread and exposes capture / analyze / settings / recent /
backend-management from the tray menu. Dynamic submenus (monitors, windows,
recent, providers) and the status icon refresh on a timer.

Threading model: tkinter is NOT thread-safe, so all Tk work must run on the main
thread. run_tray() runs the pystray icon detached (its own thread) and turns the
main thread into a UI dispatch loop (_ui_loop). Menu callbacks fire on pystray's
worker thread and marshal ALL dialog / region-overlay work to the main thread via
_ui_call (blocking until it returns).

(GUI shown from the worker thread renders but never receives input — its buttons
don't respond. This is true for Tk *and* for native Win32 message boxes here, so
every dialog, alerts included, is marshaled to the main thread.)

UI strings are localized via core.i18n.tr (Korean if the OS prefers Korean,
otherwise English).
"""

from __future__ import annotations

import functools
import json
import queue
import threading
from pathlib import Path

from ..core import clipboard, credentials
from ..core import config as cfg
from ..core.capture_service import perform_capture, register_image
from ..core.environment import EnvironmentChecker
from ..core.i18n import tr
from ..core.models import ProviderConfig
from ..server import host

_PROVIDER_TYPES = ["anthropic", "openai", "openrouter", "custom", "ollama"]
_MAX_WINDOWS = 30
_REFRESH_SEC = 5

# Status color -> RGBA stroke for the drawn aperture glyph.
# "green" (all-OK) is intentionally absent: like the macOS template icon, the OK
# state adapts to the taskbar theme (white on a dark taskbar, black on a light
# one) — see _status_rgb(). yellow/red stay colored because they signal status.
_STATUS_RGB = {
    "yellow": (245, 166, 35, 255),
    "red": (255, 59, 48, 255),
    "gray": (142, 142, 147, 255),
}


def _taskbar_uses_light_theme() -> bool:
    """True if the Windows taskbar is light (so the tray icon should be dark)."""
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return bool(value)
    except OSError:
        return False  # Windows default is a dark taskbar -> white icon


def _status_rgb(color: str, light: bool):
    """Stroke color for a status. OK adapts to the taskbar theme (macOS parity)."""
    if color == "green":
        return (0, 0, 0, 255) if light else (255, 255, 255, 255)
    return _STATUS_RGB.get(color, _STATUS_RGB["gray"])

_RECOMMENDED_MODEL = {"anthropic": "claude-sonnet-4-6", "openai": "gpt-5.4",
                      "openrouter": "anthropic/claude-sonnet-4.6", "ollama": "llava:7b"}

# LLM-facing: always English (models are more reliable with English instructions).
_ANALYZE_PROMPT = (
    "Find overlapping/broken parts, misalignment, and clipped/occluded elements "
    "in this UI, and explain them along with the likely CSS/style areas to fix."
)


# --------------------------------------------------------------------------- #
# Status icon — the brand aperture, drawn with PIL (no SVG rasterizer on Windows)
# --------------------------------------------------------------------------- #
# Geometry mirrors src/vgmcp/assets/aperture.svg (the macOS source of truth):
# a circle + 6 iris blades in a 20-unit space, after the SVG's net translate
# (-2, -2). Keep in sync if aperture.svg ever changes.
#
# NOTE: unlike macOS (where rumps renders the glyph at a fixed 20pt and it needs
# ~13% baked-in padding to not fill the bar), the Windows tray scales this image
# into its own slot — extra interior padding just makes the glyph read too small.
# So we run the OPPOSITE way here: a tight 20-unit viewBox (the glyph's native
# extent) so it fills as much of the tray slot as possible. The glyph is centered
# on (10, 10) and its 1.8 stroke's outer edge lands at ~0.1..19.9 — only ~0.1
# units of margin per side, so this is effectively the maximum size before the
# stroke would clip against the canvas edge.
_APERTURE_VB = 20.0
_APERTURE_CIRCLE = (10.0, 10.0, 9.0)  # cx, cy, r
_APERTURE_LINES = (
    (10.0, 1.0, 13.4384781, 10.6277387),
    (2.20577125, 5.5, 12.2628766, 7.33606),
    (2.20577125, 14.5, 8.8243984, 6.70832125),
    (10.0, 19.0, 6.56152188, 9.3722612),
    (17.7942287, 14.5, 7.73712344, 12.66394),
    (17.7942288, 5.5, 11.1756016, 13.2916788),
)
_APERTURE_STROKE = 1.8  # in viewBox units

# Generated icons cached by (color, light_theme, size) — the aperture is drawn
# once per distinct appearance (Windows' analogue of macOS icons.pregenerate).
_ICON_CACHE: dict[tuple, object] = {}


def _status_image(color: str, size: int = 64):
    """Render the aperture icon in the status color (4x supersampled, round caps).

    Cached per (color, taskbar theme, size); redrawn only when one of those
    changes."""
    light = _taskbar_uses_light_theme()
    key = (color, light, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    from PIL import Image, ImageDraw  # noqa: PLC0415

    rgb = _status_rgb(color, light)
    ss = 4  # supersample, then downscale for smooth (antialiased) edges
    res = size * ss
    u = res / _APERTURE_VB  # units -> supersampled pixels
    width = max(1, round(_APERTURE_STROKE * u))
    cap = width / 2.0  # round-cap radius

    img = Image.new("RGBA", (res, res), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy, r = (v * u for v in _APERTURE_CIRCLE)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=rgb, width=width)

    for x1, y1, x2, y2 in _APERTURE_LINES:
        p1 = (x1 * u, y1 * u)
        p2 = (x2 * u, y2 * u)
        draw.line([p1, p2], fill=rgb, width=width)
        for px, py in (p1, p2):  # round line caps
            draw.ellipse([px - cap, py - cap, px + cap, py + cap], fill=rgb)

    result = img.resize((size, size), Image.LANCZOS)
    _ICON_CACHE[key] = result
    return result


# --------------------------------------------------------------------------- #
# Main-thread UI marshaling
# --------------------------------------------------------------------------- #
_ui_queue: "queue.Queue" = queue.Queue()
_QUIT = object()


def _ui_loop() -> None:
    """Run on the main thread: execute queued UI jobs until quit (run_tray)."""
    while True:
        job = _ui_queue.get()
        if job is _QUIT:
            return
        job()


def _ui_call(fn):
    """Run fn() on the main UI thread and return its result (blocking).

    Called inline if we're already on the main thread; otherwise the job is
    queued for _ui_loop and the caller blocks until it finishes.
    """
    if threading.current_thread() is threading.main_thread():
        return fn()
    box: dict = {}
    done = threading.Event()

    def job() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller thread
            box["error"] = exc
        finally:
            done.set()

    _ui_queue.put(job)
    done.wait()
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _on_ui(fn):
    """Decorator: always execute the wrapped tkinter dialog on the main thread."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return _ui_call(lambda: fn(*args, **kwargs))
    return wrapper


# --------------------------------------------------------------------------- #
# Dialog helpers
# --------------------------------------------------------------------------- #
def _new_root():
    import tkinter as tk  # noqa: PLC0415

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


@_on_ui
def _alert(title: str, message: str, kind: str = "info") -> None:
    from tkinter import messagebox  # noqa: PLC0415

    root = _new_root()
    try:
        if kind == "error":
            messagebox.showerror(title, message, parent=root)
        elif kind == "warning":
            messagebox.showwarning(title, message, parent=root)
        else:
            messagebox.showinfo(title, message, parent=root)
    finally:
        root.destroy()


@_on_ui
def _confirm(title: str, message: str) -> bool:
    from tkinter import messagebox  # noqa: PLC0415

    root = _new_root()
    try:
        return bool(messagebox.askokcancel(title, message, parent=root))
    finally:
        root.destroy()


@_on_ui
def _text_input(message: str, title: str = "VGMCP", default: str = "",
                secure: bool = False, width: int = 46) -> str | None:
    """Single-line input dialog. Fixed (non-resizable) window auto-sized to its
    contents, with a wide entry. `width` is the entry width in characters
    (bump it for long values like API keys). Returns the text, or None if
    cancelled."""
    import tkinter as tk  # noqa: PLC0415
    from tkinter import ttk  # noqa: PLC0415

    root = _new_root()
    root.deiconify()
    root.title(title)
    root.resizable(False, False)  # fixed size — no clipped controls / dead padding
    result: dict[str, str | None] = {"value": None}

    ttk.Label(root, text=message, wraplength=max(360, width * 7), justify="left").pack(
        padx=16, pady=(16, 8), anchor="w")
    var = tk.StringVar(value=default)
    entry = ttk.Entry(root, textvariable=var, width=width, show=("*" if secure else ""))
    entry.pack(padx=16, pady=4, fill="x")

    def on_ok() -> None:
        result["value"] = var.get().strip()
        root.destroy()

    def on_cancel() -> None:
        result["value"] = None
        root.destroy()

    btns = ttk.Frame(root)
    btns.pack(padx=16, pady=(8, 16), anchor="e")
    ttk.Button(btns, text=tr("확인", "OK"), command=on_ok).pack(side="left", padx=4)
    ttk.Button(btns, text=tr("취소", "Cancel"), command=on_cancel).pack(side="left", padx=4)
    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.bind("<Return>", lambda _e: on_ok())
    root.bind("<Escape>", lambda _e: on_cancel())
    entry.focus_set()
    entry.icursor("end")
    root.update_idletasks()
    root.lift()
    root.focus_force()
    root.mainloop()
    return result["value"]


@_on_ui
def _multiline_input(message: str, title: str = "VGMCP", default: str = "") -> str | None:
    """Multi-line text editor (scrollable) for longer values like the clipboard
    template. Fixed, near-square window. Returns the text, or None if cancelled."""
    from tkinter import scrolledtext, ttk  # noqa: PLC0415

    root = _new_root()
    root.deiconify()
    root.title(title)
    root.geometry("520x500")
    root.resizable(False, False)  # fixed size
    result: dict[str, str | None] = {"value": None}

    ttk.Label(root, text=message, wraplength=480, justify="left").pack(
        padx=16, pady=(16, 8), anchor="w")
    txt = scrolledtext.ScrolledText(root, wrap="word", undo=True)
    txt.insert("1.0", default)
    txt.pack(padx=16, pady=4, fill="both", expand=True)

    def on_ok() -> None:
        result["value"] = txt.get("1.0", "end-1c")  # drop Tk's trailing newline
        root.destroy()

    def on_cancel() -> None:
        result["value"] = None
        root.destroy()

    btns = ttk.Frame(root)
    btns.pack(padx=16, pady=(8, 16), anchor="e")
    ttk.Button(btns, text=tr("확인", "OK"), command=on_ok).pack(side="left", padx=4)
    ttk.Button(btns, text=tr("취소", "Cancel"), command=on_cancel).pack(side="left", padx=4)
    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.bind("<Escape>", lambda _e: on_cancel())
    root.update_idletasks()
    root.lift()
    root.focus_force()
    txt.focus_set()
    root.mainloop()
    return result["value"]


@_on_ui
def _choose_from_list(message: str, title: str, options: list[str],
                      default_index: int = 0) -> str | None:
    """Dropdown selection dialog (so the user picks from a list, avoiding typos)."""
    import tkinter as tk  # noqa: PLC0415
    from tkinter import ttk  # noqa: PLC0415

    root = _new_root()
    root.deiconify()
    root.title(title)
    root.resizable(False, False)
    chosen: dict[str, str | None] = {"value": None}

    ttk.Label(root, text=message, wraplength=320, justify="left").pack(
        padx=16, pady=(16, 8))
    var = tk.StringVar(value=options[default_index] if options else "")
    combo = ttk.Combobox(root, textvariable=var, values=options, state="readonly", width=34)
    combo.pack(padx=16, pady=4)
    if options:
        combo.current(default_index)

    def on_ok() -> None:
        chosen["value"] = var.get()
        root.destroy()

    def on_cancel() -> None:
        chosen["value"] = None
        root.destroy()

    btns = ttk.Frame(root)
    btns.pack(padx=16, pady=(8, 16))
    ttk.Button(btns, text=tr("확인", "OK"), command=on_ok).pack(side="left", padx=4)
    ttk.Button(btns, text=tr("취소", "Cancel"), command=on_cancel).pack(side="left", padx=4)
    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.bind("<Return>", lambda _e: on_ok())
    root.bind("<Escape>", lambda _e: on_cancel())
    root.update_idletasks()
    root.lift()
    root.focus_force()
    root.mainloop()
    return chosen["value"]


@_on_ui
def _pick_dir() -> str | None:
    from tkinter import filedialog  # noqa: PLC0415

    root = _new_root()
    try:
        path = filedialog.askdirectory(parent=root)
        return path or None
    finally:
        root.destroy()


@_on_ui
def _pick_file() -> str | None:
    from tkinter import filedialog  # noqa: PLC0415

    root = _new_root()
    try:
        path = filedialog.askopenfilename(
            parent=root,
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        return path or None
    finally:
        root.destroy()


@_on_ui
def _show_result(res: dict, text: str) -> None:
    """Scrollable result window with a Copy button (peer of macOS _show_result)."""
    from tkinter import scrolledtext, ttk  # noqa: PLC0415

    root = _new_root()
    root.deiconify()
    root.title(tr("VGMCP 분석 결과", "VGMCP analysis result"))
    status = res.get("status", "?")
    ttk.Label(
        root,
        text=tr(f"분석 결과 (status: {status}). 아래는 원본 출력(JSON)입니다.",
                f"Analysis result (status: {status}). Raw output (JSON) below."),
        wraplength=560, justify="left",
    ).pack(padx=12, pady=(12, 6), anchor="w")
    box = scrolledtext.ScrolledText(root, width=80, height=22, wrap="word")
    box.insert("1.0", text)
    box.pack(padx=12, pady=4, fill="both", expand=True)

    def on_copy() -> None:
        clipboard.copy_to_clipboard(box.get("1.0", "end-1c"))

    btns = ttk.Frame(root)
    btns.pack(padx=12, pady=(6, 12), anchor="e")
    ttk.Button(btns, text=tr("클립보드에 복사", "Copy to clipboard"),
               command=on_copy).pack(side="left", padx=4)
    ttk.Button(btns, text=tr("닫기", "Close"), command=root.destroy).pack(side="left", padx=4)
    root.lift()
    root.focus_force()
    root.mainloop()


# --------------------------------------------------------------------------- #
# Tray icon — open the menu on left-click too (macOS menu-bar parity)
# --------------------------------------------------------------------------- #
def _make_clickable_icon(pystray, name, image, title, menu):
    """Build a tray Icon whose context menu opens on BOTH left- and right-click.

    pystray's Win32 backend only pops the menu on right-click (left-click runs
    the default item). For parity with the macOS menu-bar app — where a single
    click shows the menu — we subclass the backend Icon and remap a left-button
    release to a right-button release inside `_on_notify`. If pystray's internals
    ever change, we fall back to the stock right-click-only Icon.
    """
    try:
        from pystray._util import win32  # noqa: PLC0415

        class _ClickMenuIcon(pystray.Icon):
            def _on_notify(self, wparam, lparam):
                if lparam == win32.WM_LBUTTONUP:
                    lparam = win32.WM_RBUTTONUP  # show the menu on a plain click
                return super()._on_notify(wparam, lparam)

        return _ClickMenuIcon(name, icon=image, title=title, menu=menu)
    except Exception:  # noqa: BLE001 — internal API drift: degrade gracefully
        return pystray.Icon(name, icon=image, title=title, menu=menu)


# --------------------------------------------------------------------------- #
# Tray app
# --------------------------------------------------------------------------- #
class WindowsTrayApp:
    def __init__(self) -> None:
        import pystray  # noqa: PLC0415

        self._pystray = pystray
        self.checker = EnvironmentChecker()
        self._stop = threading.Event()
        self._icon_sig: tuple | None = None  # (color, light) last applied to the tray
        self.icon = _make_clickable_icon(
            pystray, "vgmcp", _status_image("gray"), "VGMCP", self._build_menu())

    # ---- status ---------------------------------------------------------- #
    def _status_color(self) -> str:
        try:
            if self.checker.check_full().ok:
                return "green"
            if self.checker.check_for_capture().ok:
                return "yellow"  # capture works, provider/credential missing
        except Exception:  # noqa: BLE001
            return "red"
        return "red"

    def _status_title(self, color: str) -> str:
        label = (tr("상태: 정상", "Status: OK") if color == "green"
                 else tr("상태: 조치 필요", "Status: action needed"))
        return label

    # ---- menu build ------------------------------------------------------ #
    def _build_menu(self):
        p = self._pystray
        color = self._status_color()
        Item, Menu = p.MenuItem, p.Menu
        return Menu(
            Item(self._status_title(color), self._on_recheck),
            Menu.SEPARATOR,
            Item(tr("캡처", "Capture"), self._capture_menu()),
            Item(tr("이미지 파일 열기", "Open image file"), self._on_open_image),
            Item(tr("최근 이미지", "Recent images"), self._recent_menu()),
            Menu.SEPARATOR,
            Item(tr("마지막 이미지 분석 (테스트)", "Analyze last image (test)"),
                 self._on_analyze_last,
                 enabled=lambda _i: not cfg.load_config().self_analysis_mode),
            Item(tr("설정", "Settings"), self._settings_menu()),
            Menu.SEPARATOR,
            Item(tr("종료", "Quit"), self._on_quit),
        )

    def _capture_menu(self):
        from ..capture import get_capture_backend  # noqa: PLC0415

        p = self._pystray
        Item, Menu = p.MenuItem, p.Menu
        items: list = []
        backend = get_capture_backend()
        if backend is not None:
            try:
                for m in backend.list_monitors():
                    label = tr(f"모니터 {m.index} ({m.width}×{m.height})",
                               f"Monitor {m.index} ({m.width}×{m.height})")
                    items.append(Item(label, self._make_monitor_cb(m.index)))
            except Exception:  # noqa: BLE001
                pass
            win_items: list = []
            try:
                for wi in backend.list_windows()[:_MAX_WINDOWS]:
                    label = f"{wi.app_name} — {wi.title[:30]}" if wi.title else wi.app_name
                    win_items.append(Item(label, self._make_window_cb(wi.window_id)))
            except Exception:  # noqa: BLE001
                pass
            if not win_items:
                win_items.append(Item(tr("(창 없음)", "(no windows)"), None, enabled=False))
            items.append(Item(tr("앱 창 선택 캡처", "Capture an app window"), Menu(*win_items)))
        items.append(Item(tr("영역 선택 캡처 (드래그)", "Capture a region (drag)"),
                          self._on_capture_region))
        return Menu(*items)

    def _recent_menu(self):
        p = self._pystray
        Item, Menu = p.MenuItem, p.Menu
        config = cfg.load_config()
        # Self-heal: drop entries whose files were deleted/moved (plan §4.1).
        if config.prune_recent():
            config = cfg.update_config(lambda latest: latest.prune_recent())
        items = [Item(tr("타겟 폴더 열기", "Open target folder"), self._on_open_target_folder)]
        recents = [Item(Path(pth).name, self._make_recent_cb(pth))
                   for pth in config.recent_images]
        items += recents or [Item(tr("(최근 이미지 없음)", "(no recent images)"),
                                  None, enabled=False)]
        return Menu(*items)

    def _settings_menu(self):
        p = self._pystray
        Item, Menu = p.MenuItem, p.Menu
        from ..core import autostart  # noqa: PLC0415

        return Menu(
            Item(tr("타겟 폴더 설정...", "Set target folder…"), self._on_set_target_folder),
            Item(tr("셀프 분석 모드 사용", "Use self-analysis mode"),
                 self._on_toggle_self_analysis,
                 checked=lambda _i: cfg.load_config().self_analysis_mode),
            Item(tr("비전 백엔드 관리", "Manage vision backends"), self._backend_menu()),
            Item(tr("클립보드 템플릿 편집...", "Edit clipboard template…"), self._on_edit_template),
            Item(tr("자동 클립보드 복사", "Auto-copy to clipboard"),
                 self._on_toggle_autoclip, checked=lambda _i: cfg.load_config().clipboard_auto),
            Item(tr("이미지 열기 시 타겟 폴더로 복사", "Copy opened images to target folder"),
                 self._on_toggle_copyorig, checked=lambda _i: cfg.load_config().copy_original),
            Item(tr("로그인 시 자동 시작", "Start at login"),
                 self._on_toggle_autostart, checked=lambda _i: autostart.is_enabled()),
        )

    def _backend_menu(self):
        p = self._pystray
        Item, Menu = p.MenuItem, p.Menu
        config = cfg.load_config()
        default_id = config.default_provider_id
        items: list = []
        for prov in config.providers:
            mark = "✓ " if prov.id == default_id else "   "
            sub_items = [Item(tr("모델명 변경", "Change model name"),
                              self._make_changemodel_cb(prov.id))]
            sub_items.append(Item(tr("기본값으로 설정", "Set as default"),
                                  self._make_setdefault_cb(prov.id)))
            if not prov.is_local:
                label = (tr("외부 전송 동의 해제", "Revoke external-send consent")
                         if prov.consented else tr("외부 전송 동의", "Allow external send"))
                sub_items.append(Item(label, self._make_consent_cb(prov.id, not prov.consented)))
            sub_items.append(Item(tr("삭제", "Remove"), self._make_removeprovider_cb(prov.id)))
            items.append(Item(f"{mark}{prov.id} ({prov.type})", Menu(*sub_items)))
        if not config.providers:
            items.append(Item(tr("(등록된 provider 없음)", "(no providers registered)"),
                              None, enabled=False))
        items.append(Item(tr("추가...", "Add…"), self._on_add_provider))
        return Menu(*items)

    # ---- refresh --------------------------------------------------------- #
    def _refresh(self) -> None:
        try:
            # Update the tray icon only when its appearance actually changes
            # (status or taskbar theme), avoiding a redundant Shell_NotifyIcon
            # call every tick. The menu is always rebuilt (dynamic contents).
            color = self._status_color()
            sig = (color, _taskbar_uses_light_theme())
            if sig != self._icon_sig:
                self.icon.icon = _status_image(color)
                self._icon_sig = sig
            self.icon.menu = self._build_menu()
            self.icon.update_menu()
        except Exception as exc:  # noqa: BLE001 — never let the timer kill the app
            print(f"[vgmcp tray] refresh error: {exc}")

    def _timer_loop(self) -> None:
        while not self._stop.wait(_REFRESH_SEC):
            self._refresh()

    # ---- capture callbacks ----------------------------------------------- #
    def _make_monitor_cb(self, index: int):
        return lambda _i=None, _it=None: self._capture(target="monitor", monitor_index=index)

    def _make_window_cb(self, window_id: int):
        return lambda _i=None, _it=None: self._capture(target="window", window_id=window_id)

    def _on_capture_region(self, _icon=None, _item=None) -> None:
        self._capture(target="region_interactive")

    def _capture(self, **kwargs) -> None:
        # The interactive region overlay is Tk, so it must run on the main thread;
        # monitor/window/region captures have no UI and run on the caller thread.
        if kwargs.get("target") == "region_interactive":
            result = _ui_call(lambda: perform_capture(**kwargs))
        else:
            result = perform_capture(**kwargs)
        status = result.get("status")
        if status == "ok":
            self._refresh()  # success is silent
        elif status == "cancelled":
            pass
        else:
            _alert(tr("캡처 실패", "Capture failed"),
                   result.get("message", status or tr("오류", "error")), kind="error")

    def _on_open_image(self, _icon=None, _item=None) -> None:
        path = _pick_file()
        if not path:
            return
        result = register_image(path)
        if result.get("status") == "ok":
            self._refresh()
        else:
            _alert(tr("등록 실패", "Register failed"),
                   result.get("message", tr("오류", "error")), kind="error")

    def _make_recent_cb(self, path: str):
        def cb(_icon=None, _item=None) -> None:
            config = cfg.load_config()
            if not Path(path).exists():
                if config.prune_recent():
                    cfg.update_config(lambda latest: latest.prune_recent())
                self._refresh()
                _alert(tr("파일 없음", "File missing"),
                       tr("파일이 더 이상 없어 최근 목록에서 제거했습니다.",
                          "File no longer exists; removed from recents."), kind="warning")
                return
            ok, _t = clipboard.copy_prompt(path, config.clipboard_template)
            if not ok:
                _alert(tr("복사 실패", "Copy failed"), Path(path).name, kind="error")
        return cb

    def _on_open_target_folder(self, _icon=None, _item=None) -> None:
        import os  # noqa: PLC0415

        folder = cfg.load_config().target_folder
        Path(folder).mkdir(parents=True, exist_ok=True)
        os.startfile(folder)  # noqa: S606 — open in Explorer (Windows)

    # ---- analysis -------------------------------------------------------- #
    def _on_analyze_last(self, _icon=None, _item=None) -> None:
        config = cfg.load_config()
        if config.self_analysis_mode:
            return
        # Skip stale (deleted/moved) entries so we analyze a real file.
        if config.prune_recent():
            config = cfg.update_config(lambda latest: latest.prune_recent())
            self._refresh()
        if not config.recent_images:
            _alert(tr("분석 불가", "Can't analyze"),
                   tr("최근 이미지가 없습니다. 먼저 캡처하세요.",
                      "No recent image. Capture one first."), kind="warning")
            return
        provider = config.effective_default()
        if provider is None:
            _alert(tr("분석 불가", "Can't analyze"),
                   tr("등록된 비전 백엔드가 없습니다. 설정에서 추가하세요.",
                      "No vision backend. Add one in Settings."), kind="warning")
            return
        if not provider.is_local and not provider.consented:
            if not self._confirm_consent(provider):
                return
            cfg.update_config(lambda latest: latest.set_consent(provider.id, True))
            self._refresh()
        image = config.recent_images[0]

        def worker() -> None:
            from ..server.vision_service import run_analysis  # noqa: PLC0415

            res = run_analysis(Path(image), _ANALYZE_PROMPT, None)
            text = json.dumps(res, ensure_ascii=False, indent=2)
            _show_result(res, text)

        threading.Thread(target=worker, daemon=True).start()

    def _confirm_consent(self, provider) -> bool:
        return _confirm(
            tr("외부 전송 동의", "External transmission consent"),
            tr(
                f"'{provider.label or provider.id}'({provider.type})로 스크린샷이 외부 서버에 "
                "전송됩니다. 민감한 화면이 포함될 수 있습니다. 계속할까요?\n\n"
                "(외부 전송 없이 사용하려면 로컬 Ollama 백엔드를 등록하세요.)",
                f"Screenshots will be sent to '{provider.label or provider.id}'"
                f"({provider.type}), an external server. They may contain sensitive "
                "content. Continue?\n\n"
                "(To avoid external transmission, register the local Ollama backend.)",
            ),
        )

    # ---- settings callbacks ---------------------------------------------- #
    def _on_set_target_folder(self, _icon=None, _item=None) -> None:
        path = _pick_dir()
        if not path:
            return
        cfg.update_config(lambda config: setattr(config, "target_folder", path))

    def _on_edit_template(self, _icon=None, _item=None) -> None:
        config = cfg.load_config()
        current = config.clipboard_template or clipboard.DEFAULT_TEMPLATE
        new = _multiline_input(
            tr("클립보드 프롬프트 템플릿 ({image_path}, {filename} 사용 가능)",
               "Clipboard prompt template ({image_path}, {filename} available)"),
            tr("템플릿 편집", "Edit template"), current)
        if new is None:
            return
        value = new.strip() or None
        cfg.update_config(lambda latest: setattr(latest, "clipboard_template", value))

    def _on_toggle_self_analysis(self, _icon=None, _item=None) -> None:
        config = cfg.load_config()
        if not config.self_analysis_mode and not _confirm(
            tr("셀프 분석 모드 사용", "Use self-analysis mode"),
            tr(
                "셀프 분석 모드는 비전 백엔드 요청 없이 이미지만 캡쳐하여 LLM 모델에게 "
                "직접 분석을 요청하는 기능입니다. 비전 기능이 없는 LLM 모델의 경우 이미지 "
                "분석이 불가능해집니다. 이미 시작된 분석 요청은 완료될 수 있습니다.",
                "Self-analysis mode captures only the image without requesting a vision "
                "backend and asks the LLM model to analyze it directly. LLM models without "
                "vision capabilities will not be able to analyze images. Analysis requests "
                "that have already started may finish.",
            ),
        ):
            return
        enabled = not config.self_analysis_mode
        cfg.update_config(lambda latest: setattr(latest, "self_analysis_mode", enabled))
        self._refresh()

    def _on_toggle_autoclip(self, _icon=None, _item=None) -> None:
        cfg.update_config(
            lambda config: setattr(config, "clipboard_auto", not config.clipboard_auto)
        )
        self._refresh()

    def _on_toggle_copyorig(self, _icon=None, _item=None) -> None:
        cfg.update_config(
            lambda config: setattr(config, "copy_original", not config.copy_original)
        )
        self._refresh()

    def _on_toggle_autostart(self, _icon=None, _item=None) -> None:
        from ..core import autostart  # noqa: PLC0415

        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()
        self._refresh()

    # ---- backend management ---------------------------------------------- #
    def _make_changemodel_cb(self, pid: str):
        def cb(_icon=None, _item=None) -> None:
            config = cfg.load_config()
            provider = config.get_provider(pid)
            if provider is None:
                return
            ptype = provider.type
            current = provider.model or ""
            if ptype == "ollama":
                mmsg = tr(
                    "모델명 (추천: llava:7b). 추론(thinking) 모델(예: qwen3-vl)은 응답이 비거나 "
                    "불안정할 수 있어 권장하지 않습니다. 비우면 기본값(llava:7b) 사용.",
                    "Model name (recommended: llava:7b). Reasoning/thinking models (e.g. "
                    "qwen3-vl) can return empty/unstable output — not recommended. "
                    "Blank = default (llava:7b).")
            elif ptype in _RECOMMENDED_MODEL and ptype != "ollama":
                mmsg = tr(f"모델명 (추천: {_RECOMMENDED_MODEL[ptype]}). 비우면 기본값 사용.",
                          f"Model name (recommended: {_RECOMMENDED_MODEL[ptype]}). "
                          "Blank = default.")
            else:
                mmsg = tr("모델명 (비우면 기본값 사용).", "Model name (blank = default).")
            model = _text_input(mmsg, tr("모델명 변경", "Change model name"), current)
            if model is None:
                return  # cancelled
            def update_model(latest) -> None:
                current_provider = latest.get_provider(pid)
                if current_provider is not None:
                    current_provider.model = model or ""

            cfg.update_config(update_model)
            self._refresh()
        return cb

    def _make_setdefault_cb(self, pid: str):
        def cb(_icon=None, _item=None) -> None:
            cfg.update_config(lambda latest: latest.set_default_provider(pid))
            self._refresh()
        return cb

    def _make_consent_cb(self, pid: str, grant: bool):
        def cb(_icon=None, _item=None) -> None:
            cfg.update_config(lambda latest: latest.set_consent(pid, grant))
            self._refresh()
        return cb

    def _make_removeprovider_cb(self, pid: str):
        def cb(_icon=None, _item=None) -> None:
            config = cfg.load_config()
            prov = config.get_provider(pid)
            if prov and prov.key_ref:
                credentials.delete_key(prov.key_ref)
            cfg.update_config(lambda latest: latest.remove_provider(pid))
            self._refresh()
        return cb

    def _on_add_provider(self, _icon=None, _item=None) -> None:
        title = tr("백엔드 추가", "Add backend")
        ptype = _choose_from_list(
            tr("등록할 provider 종류를 선택하세요.", "Choose a provider type."),
            title, _PROVIDER_TYPES)
        if ptype is None:
            return
        config = cfg.load_config()
        prompt = tr(
            "provider 고유 id를 입력하세요. (VGMCP 내부 구분용 이름이며 외부로 전송되지 않습니다.)\n"
            "같은 종류를 여러 개 등록하려면 서로 다르게 지정하세요.",
            "Enter a unique provider id. (Internal VGMCP label only — never sent "
            "externally.)\nUse different ids to register several of the same type.")
        while True:
            pid = _text_input(prompt, title, ptype)
            if not pid:
                return
            if config.get_provider(pid) is None:
                break
            _alert(tr("중복된 id", "Duplicate id"),
                   tr(f"'{pid}' 는 이미 등록되어 있습니다. 다른 id를 입력하세요.",
                      f"'{pid}' already exists. Enter a different id."), kind="warning")
        default_model = _RECOMMENDED_MODEL.get(ptype, "")
        if ptype == "ollama":
            mmsg = tr(
                "모델명 (추천: llava:7b). 추론(thinking) 모델(예: qwen3-vl)은 응답이 비거나 "
                "불안정할 수 있어 권장하지 않습니다. 비우면 기본값(llava:7b) 사용.",
                "Model name (recommended: llava:7b). Reasoning/thinking models (e.g. "
                "qwen3-vl) can return empty/unstable output — not recommended. "
                "Blank = default (llava:7b).")
        elif ptype in _RECOMMENDED_MODEL:
            mmsg = tr(f"모델명 (추천: {_RECOMMENDED_MODEL[ptype]}). 비우면 기본값 사용.",
                      f"Model name (recommended: {_RECOMMENDED_MODEL[ptype]}). Blank = default.")
        else:
            mmsg = tr("모델명 (비우면 기본값 사용).", "Model name (blank = default).")
        model = _text_input(mmsg, title, default_model) or ""
        base_url = None
        if ptype == "custom":
            base_url = _text_input(
                tr("base_url (OpenAI 호환 엔드포인트)", "base_url (OpenAI-compatible endpoint)"),
                title, "", width=64)
            if not base_url:
                _alert(tr("추가 실패", "Add failed"),
                       tr("custom에는 base_url이 필요합니다.", "custom requires a base_url."),
                       kind="error")
                return
        key_ref = None
        if ptype != "ollama":
            key = _text_input(tr("API 키 (비우면 환경변수 사용)", "API key (blank = use env var)"),
                              title, "", secure=True, width=64)
            if key:
                key_ref = f"provider:{pid}"
                credentials.set_key(key_ref, key)
        provider = ProviderConfig(
            id=pid, type=ptype, label=pid, model=model, base_url=base_url, key_ref=key_ref)
        try:
            cfg.update_config(lambda latest: latest.add_provider(provider))
        except ValueError:
            if key_ref:
                credentials.delete_key(key_ref)
            _alert(tr("추가 실패", "Add failed"),
                   tr("동일한 id가 방금 등록되었습니다.",
                      "The same id was just registered."), kind="warning")
            return
        self._refresh()

    # ---- onboarding / lifecycle ------------------------------------------ #
    def maybe_onboard(self) -> None:
        config = cfg.load_config()
        if config.onboarding_consent_shown:
            return
        _alert(
            tr("VGMCP 시작하기", "Getting started with VGMCP"),
            tr(
                "1) 트레이 아이콘에서 모니터/창/영역을 캡처할 수 있습니다.\n\n"
                "2) 클라우드 비전 백엔드(Anthropic/OpenAI/OpenRouter/커스텀)를 쓰면 캡처 이미지가 "
                "외부 서버로 전송됩니다. 각 백엔드 최초 사용 시 동의를 묻습니다.\n\n"
                "3) 외부 전송 없이 쓰려면 로컬 Ollama 백엔드를 등록하세요.",
                "1) Capture a monitor / window / region from the tray icon.\n\n"
                "2) Cloud vision backends (Anthropic/OpenAI/OpenRouter/custom) send the "
                "captured image to an external server. You'll be asked to consent on first "
                "use of each backend.\n\n"
                "3) To keep everything local, register the Ollama backend.",
            ),
        )
        cfg.update_config(
            lambda latest: setattr(latest, "onboarding_consent_shown", True)
        )

    def _on_recheck(self, _icon=None, _item=None) -> None:
        self._refresh()
        items = self.checker.detailed()
        lines = []
        for label, ok, detail in items:
            mark = "OK" if ok else "X"
            lines.append(f"[{mark}] {label}" if ok else f"[{mark}] {label} — {detail}")
        n_fail = sum(1 for _, ok, _ in items if not ok)
        summary = (tr("모든 항목 정상", "All checks passed") if n_fail == 0
                   else tr(f"문제 {n_fail}건 — 위 항목을 확인하세요.",
                           f"{n_fail} issue(s) — see the items above."))
        _alert(tr("환경 재검사 결과", "Environment check"),
               "\n".join(lines) + "\n\n" + tr("종합: ", "Summary: ") + summary)

    def _on_quit(self, _icon=None, _item=None) -> None:
        self._stop.set()
        self.icon.stop()
        _ui_queue.put(_QUIT)  # release the main-thread UI loop

    def run(self) -> None:
        threading.Thread(target=self._timer_loop, name="vgmcp-tray-refresh",
                         daemon=True).start()
        # Show the first-run notice shortly after startup (native box, any thread).
        threading.Timer(0.5, self.maybe_onboard).start()
        # Icon on its own thread; the main thread becomes the Tk dispatch loop so
        # dialog buttons actually respond (see module docstring).
        self.icon.run_detached()
        _ui_loop()


def build_app() -> WindowsTrayApp:
    """Construct the tray app (without running the GUI loop) — used by smoke tests."""
    return WindowsTrayApp()


def _ensure_std_streams() -> None:
    """pythonw.exe (the console-less launcher used by start_win.bat / autostart)
    leaves sys.stdout and sys.stderr as None. FastMCP/uvicorn print a banner and
    log lines, so the embedded host thread would crash on its first write and the
    port would never open (the tray icon still appears). Point the missing streams
    at a log file so the host starts — and so errors are recoverable.
    """
    import sys  # noqa: PLC0415

    if sys.stdout is not None and sys.stderr is not None:
        return
    sink = None
    try:
        from ..core.config import config_dir  # noqa: PLC0415

        log_dir = config_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        sink = open(log_dir / "host.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    except OSError:
        import os  # noqa: PLC0415

        sink = open(os.devnull, "w")  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = sink
    if sys.stderr is None:
        sys.stderr = sink


def run_tray() -> None:
    # Under pythonw there is no console; give the host writable streams first.
    _ensure_std_streams()
    # Make the process DPI-aware before any capture/Tk work (constructs the
    # capture backend, whose __init__ sets per-monitor DPI awareness).
    from ..capture import get_capture_backend  # noqa: PLC0415

    get_capture_backend()
    host.start_background()
    build_app().run()
