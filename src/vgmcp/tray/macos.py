"""macOS menu-bar app (plan §4).

Runs the resident HTTP host on a background thread and exposes capture /
analyze / settings / recent / backend-management from the menu bar. Dynamic
submenus (monitors, windows, recent, providers) and the status icon refresh on
a timer. Tray-initiated captures run on the main thread; the host marshals its
own captures via core.mainthread (plan §2.4.2).
"""

from __future__ import annotations

import threading
from pathlib import Path

from ..core import clipboard, credentials
from ..core import config as cfg
from ..core.capture_service import perform_capture, register_image
from ..core.environment import EnvironmentChecker
from ..core.mainthread import run_on_main
from ..core.models import ProviderConfig
from ..server import host

_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⚪"}
_PROVIDER_TYPES = ["anthropic", "openai", "openrouter", "custom", "ollama"]
_MAX_WINDOWS = 15


# --------------------------------------------------------------------------- #
# Dialog helpers (AppKit)
# --------------------------------------------------------------------------- #
def _text_input(message: str, title: str = "VGMCP", default: str = "",
                secure: bool = False) -> str | None:
    import rumps  # noqa: PLC0415

    win = rumps.Window(message=message, title=title, default_text=default,
                       ok="확인", cancel="취소", dimensions=(360, 120), secure=secure)
    resp = win.run()
    return resp.text.strip() if resp.clicked else None


def _pick_path(*, directory: bool, file_types: list[str] | None = None) -> str | None:
    from AppKit import NSOpenPanel  # noqa: PLC0415

    panel = NSOpenPanel.openPanel()
    panel.setCanChooseDirectories_(directory)
    panel.setCanChooseFiles_(not directory)
    panel.setAllowsMultipleSelection_(False)
    if file_types:
        panel.setAllowedFileTypes_(file_types)
    if panel.runModal() != 1:  # NSModalResponseOK
        return None
    urls = panel.URLs()
    return urls[0].path() if urls else None


def _notify(title: str, message: str) -> None:
    import rumps  # noqa: PLC0415

    def _post():
        rumps.notification(title, None, message)
    run_on_main(_post)


# --------------------------------------------------------------------------- #
def _make_app_class():
    import rumps  # noqa: PLC0415

    class VGMCPApp(rumps.App):
        def __init__(self) -> None:
            super().__init__("VGMCP", title=_ICON["gray"], quit_button="종료")
            self.checker = EnvironmentChecker()
            self.cap_menu = rumps.MenuItem("캡처")
            self.recent_menu = rumps.MenuItem("최근 이미지")
            self.backend_menu = rumps.MenuItem("비전 백엔드 관리")
            self.autoclip_item = rumps.MenuItem("자동 클립보드 복사", callback=self.toggle_autoclip)
            settings = rumps.MenuItem("설정")
            settings.update([
                rumps.MenuItem("타겟 폴더 설정...", callback=self.set_target_folder),
                self.backend_menu,
                rumps.MenuItem("클립보드 템플릿 편집...", callback=self.edit_template),
                self.autoclip_item,
                rumps.MenuItem("환경 재검사", callback=lambda _=None: self.refresh()),
            ])
            self.menu = [
                self.cap_menu,
                rumps.MenuItem("마지막 이미지 분석", callback=self.analyze_last),
                None,
                settings,
                self.recent_menu,
                None,
            ]
            self.refresh()
            self.timer = rumps.Timer(lambda _=None: self.refresh(), 5)
            self.timer.start()

        def stop_timer(self) -> None:
            self.timer.stop()

        # ---- refresh dynamic parts ---------------------------------------- #
        def refresh(self, _sender=None) -> None:
            try:
                self._refresh_status()
                self._refresh_capture_menu()
                self._refresh_recent_menu()
                self._refresh_backend_menu()
                config = cfg.load_config()
                self.autoclip_item.state = 1 if config.clipboard_auto else 0
            except Exception as exc:  # noqa: BLE001 — never let the timer kill the app
                self.title = _ICON["red"]
                print(f"[vgmcp tray] refresh error: {exc}")

        def _refresh_status(self) -> None:
            full = self.checker.check_full()
            if full.ok:
                self.title = _ICON["green"]
            elif self.checker.check_for_capture().ok:
                self.title = _ICON["yellow"]  # capture works, provider/cred missing
            else:
                self.title = _ICON["red"]

        def _refresh_capture_menu(self) -> None:
            from ..capture import get_capture_backend  # noqa: PLC0415

            items: list = []
            backend = get_capture_backend()
            if backend is not None:
                try:
                    for m in backend.list_monitors():
                        label = f"모니터 {m.index} ({m.width}×{m.height})"
                        items.append(rumps.MenuItem(
                            label, callback=self._make_monitor_cb(m.index)))
                except Exception:  # noqa: BLE001
                    pass
                wins_parent = rumps.MenuItem("앱 창 선택 캡처")
                try:
                    wins = backend.list_windows()[:_MAX_WINDOWS]
                    for wi in wins:
                        label = f"{wi.app_name} — {wi.title[:30]}" if wi.title else wi.app_name
                        wins_parent.add(rumps.MenuItem(
                            label, callback=self._make_window_cb(wi.window_id)))
                except Exception:  # noqa: BLE001
                    pass
                items.append(wins_parent)
            items.append(rumps.MenuItem("영역 선택 캡처 (드래그)", callback=self.cap_region))
            items.append(rumps.MenuItem("이미지 파일 열기...", callback=self.open_image))
            _set_children(self.cap_menu, items)

        def _refresh_recent_menu(self) -> None:
            config = cfg.load_config()
            items = [
                rumps.MenuItem(Path(p).name, callback=self._make_recent_cb(p))
                for p in config.recent_images
            ]
            if not items:
                items = [rumps.MenuItem("(없음)", callback=None)]
            _set_children(self.recent_menu, items)

        def _refresh_backend_menu(self) -> None:
            config = cfg.load_config()
            items: list = []
            default_id = config.default_provider_id
            for p in config.providers:
                mark = "✓ " if p.id == default_id else "   "
                sub = rumps.MenuItem(f"{mark}{p.id} ({p.type})")
                sub.add(rumps.MenuItem("기본값으로 설정", callback=self._make_setdefault_cb(p.id)))
                sub.add(rumps.MenuItem("삭제", callback=self._make_removeprovider_cb(p.id)))
                items.append(sub)
            if not config.providers:
                items.append(rumps.MenuItem("(등록된 provider 없음)", callback=None))
            items.append(rumps.MenuItem("추가...", callback=self.add_provider))
            _set_children(self.backend_menu, items)

        # ---- capture actions ---------------------------------------------- #
        def _make_monitor_cb(self, index: int):
            return lambda _=None: self._capture(target="monitor", monitor_index=index)

        def _make_window_cb(self, window_id: int):
            return lambda _=None: self._capture(target="window", window_id=window_id)

        def cap_region(self, _sender=None) -> None:
            self._capture(target="region_interactive")

        def _capture(self, **kwargs) -> None:
            result = perform_capture(**kwargs)
            status = result.get("status")
            if status == "ok":
                extra = " (클립보드 복사됨)" if result.get("clipboard_copied") else ""
                _notify("캡처 완료", f"{Path(result['path']).name}{extra}")
                self._refresh_recent_menu()
            elif status == "cancelled":
                pass
            else:
                _notify("캡처 실패", result.get("message", status or "오류"))

        def open_image(self, _sender=None) -> None:
            path = _pick_path(directory=False, file_types=["png", "jpg", "jpeg", "webp"])
            if not path:
                return
            result = register_image(path)
            if result.get("status") == "ok":
                _notify("이미지 등록", Path(path).name)
                self._refresh_recent_menu()
            else:
                _notify("등록 실패", result.get("message", "오류"))

        def _make_recent_cb(self, path: str):
            def cb(_=None) -> None:
                config = cfg.load_config()
                ok, _t = clipboard.copy_prompt(path, config.clipboard_template)
                _notify("클립보드 복사" if ok else "복사 실패", Path(path).name)
            return cb

        # ---- analysis ----------------------------------------------------- #
        def analyze_last(self, _sender=None) -> None:
            config = cfg.load_config()
            if not config.recent_images:
                _notify("분석 불가", "최근 이미지가 없습니다. 먼저 캡처하세요.")
                return
            image = config.recent_images[0]

            def worker() -> None:
                from ..server.vision_service import run_analysis  # noqa: PLC0415

                res = run_analysis(Path(image), (
                    "현재 UI에서 겹치거나 깨진 부분, 정렬 불량, 요소 가려짐/잘림을 찾아 "
                    "원인이 될 만한 CSS/스타일 영역과 함께 설명해 줘."), None)
                if res.get("status") == "ok":
                    summary = res["report"].get("summary") or "(요약 없음)"
                    _notify("분석 완료", summary[:200])
                else:
                    _notify("분석 실패", res.get("message", res.get("error_code", "오류")))

            _notify("분석 시작", Path(image).name)
            threading.Thread(target=worker, daemon=True).start()

        # ---- settings ----------------------------------------------------- #
        def set_target_folder(self, _sender=None) -> None:
            path = _pick_path(directory=True)
            if not path:
                return
            config = cfg.load_config()
            config.target_folder = path
            cfg.save_config(config)
            _notify("타겟 폴더 설정", path)

        def edit_template(self, _sender=None) -> None:
            config = cfg.load_config()
            current = config.clipboard_template or clipboard.DEFAULT_TEMPLATE
            new = _text_input("클립보드 프롬프트 템플릿 ({image_path}, {filename} 사용 가능)",
                              "템플릿 편집", current)
            if new is None:
                return
            config.clipboard_template = new or None
            cfg.save_config(config)
            _notify("템플릿 저장", "완료")

        def toggle_autoclip(self, _sender=None) -> None:
            config = cfg.load_config()
            config.clipboard_auto = not config.clipboard_auto
            cfg.save_config(config)
            self.autoclip_item.state = 1 if config.clipboard_auto else 0

        # ---- backend management ------------------------------------------- #
        def _make_setdefault_cb(self, pid: str):
            def cb(_=None) -> None:
                config = cfg.load_config()
                config.default_provider_id = pid
                cfg.save_config(config)
                self._refresh_backend_menu()
                _notify("기본 백엔드 변경", pid)
            return cb

        def _make_removeprovider_cb(self, pid: str):
            def cb(_=None) -> None:
                config = cfg.load_config()
                p = config.get_provider(pid)
                if p and p.key_ref:
                    credentials.delete_key(p.key_ref)
                config.remove_provider(pid)
                cfg.save_config(config)
                self._refresh_backend_menu()
                _notify("백엔드 삭제", pid)
            return cb

        def add_provider(self, _sender=None) -> None:
            ptype = _text_input(f"provider 유형 ({'/'.join(_PROVIDER_TYPES)})",
                                "백엔드 추가", "anthropic")
            if ptype is None:
                return
            ptype = ptype.lower()
            if ptype not in _PROVIDER_TYPES:
                _notify("추가 실패", f"알 수 없는 유형: {ptype}")
                return
            pid = _text_input("provider id (고유 이름)", "백엔드 추가", ptype)
            if not pid:
                return
            config = cfg.load_config()
            if config.get_provider(pid):
                _notify("추가 실패", f"이미 존재하는 id: {pid}")
                return
            model = _text_input("모델명 (비우면 기본값)", "백엔드 추가", "") or ""
            base_url = None
            if ptype == "custom":
                base_url = _text_input("base_url (OpenAI 호환 엔드포인트)", "백엔드 추가", "")
                if not base_url:
                    _notify("추가 실패", "custom에는 base_url이 필요합니다.")
                    return
            key_ref = None
            if ptype != "ollama":
                key = _text_input("API 키 (비우면 환경변수 사용)", "백엔드 추가", "", secure=True)
                if key:
                    key_ref = f"provider:{pid}"
                    credentials.set_key(key_ref, key)
            config.add_provider(ProviderConfig(
                id=pid, type=ptype, label=pid, model=model, base_url=base_url, key_ref=key_ref))
            cfg.save_config(config)
            self._refresh_backend_menu()
            _notify("백엔드 추가", pid)

    return VGMCPApp


def build_app():
    """Construct the tray app (without running the GUI loop) — used by smoke tests."""
    return _make_app_class()()


def run_tray() -> None:
    host.start_background()
    build_app().run()


def _set_children(parent, children) -> None:
    # MenuItem.clear() raises if its NSMenu hasn't been created yet (empty item);
    # in that case there's nothing to clear, so just add.
    try:
        parent.clear()
    except Exception:  # noqa: BLE001 — empty submenu has no NSMenu to clear yet
        pass
    for child in children:
        parent.add(child)
