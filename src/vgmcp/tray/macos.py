"""macOS menu-bar app (plan §4).

Runs the resident HTTP host on a background thread and exposes capture /
analyze / settings / recent / backend-management from the menu bar. Dynamic
submenus (monitors, windows, recent, providers) and the status icon refresh on
a timer. Tray-initiated captures run on the main thread; the host marshals its
own captures via core.mainthread (plan §2.4.2).

UI strings are localized via core.i18n.tr (Korean if the OS prefers Korean,
otherwise English).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from ..core import clipboard, credentials
from ..core import config as cfg
from ..core.capture_service import perform_capture, register_image
from ..core.environment import EnvironmentChecker
from ..core.i18n import tr
from ..core.mainthread import post_to_main, run_on_main
from ..core.models import ProviderConfig
from ..server import host

_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⚪"}
_PROVIDER_TYPES = ["anthropic", "openai", "openrouter", "custom", "ollama"]
_MAX_WINDOWS = 15

# One recommended model per cloud provider (custom/ollama intentionally omitted).
# Value = the model id prefilled; label = how it's introduced to the user.
_RECOMMENDED_MODEL = {"anthropic": "claude-sonnet-4-6", "openai": "gpt-4o",
                      "openrouter": "openai/gpt-4o"}
_RECOMMENDED_LABEL = {"anthropic": "claude-sonnet-4-6", "openai": "gpt-4o",
                      "openrouter": "openai/gpt-4o"}

# LLM-facing: always English (models are more reliable with English instructions).
_ANALYZE_PROMPT = (
    "Find overlapping/broken parts, misalignment, and clipped/occluded elements "
    "in this UI, and explain them along with the likely CSS/style areas to fix."
)


# --------------------------------------------------------------------------- #
# Dialog helpers (AppKit)
# --------------------------------------------------------------------------- #
def _aperture_nsimage(size: int, template: bool):
    """Load our aperture icon as an NSImage. As a template image it adapts to the
    dialog's light/dark appearance (so it's visible on both)."""
    from ..core import icons  # noqa: PLC0415

    try:
        from AppKit import NSImage  # noqa: PLC0415
    except ImportError:
        return None
    path = icons.get_icon("normal", size)
    if path is None:
        return None
    img = NSImage.alloc().initByReferencingFile_(str(path))
    if img is not None:
        img.setTemplate_(template)
    return img


def _brand_alert_icon(alert) -> None:
    """Replace a dialog's default (Python) app icon with our aperture icon."""
    img = _aperture_nsimage(64, template=True)
    if img is not None:
        alert.setIcon_(img)


def _alert(title: str, message: str, ok: str | None = None, cancel=None) -> int:
    """A native NSAlert (so we can brand the icon). Returns 1 for ok, 0 for cancel."""
    from AppKit import NSAlert  # noqa: PLC0415

    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_(ok or tr("확인", "OK"))
    if cancel:
        alert.addButtonWithTitle_(cancel)
    _brand_alert_icon(alert)
    return 1 if alert.runModal() == 1000 else 0


def _text_input(message: str, title: str = "VGMCP", default: str = "",
                secure: bool = False) -> str | None:
    import rumps  # noqa: PLC0415

    win = rumps.Window(message=message, title=title, default_text=default,
                       ok=tr("확인", "OK"), cancel=tr("취소", "Cancel"),
                       dimensions=(360, 120), secure=secure)
    _brand_alert_icon(win._alert)
    resp = win.run()
    return resp.text.strip() if resp.clicked else None


def _choose_from_list(message: str, title: str, options: list[str],
                      default_index: int = 0) -> str | None:
    """A combo-box (dropdown) selection dialog via NSAlert + NSPopUpButton.

    Returns the chosen option string, or None if cancelled. Used so the user
    selects from a fixed list instead of typing (avoids typos).
    """
    from AppKit import NSAlert, NSMakeRect, NSPopUpButton  # noqa: PLC0415

    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_(tr("확인", "OK"))
    alert.addButtonWithTitle_(tr("취소", "Cancel"))
    popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 280, 26), False)
    popup.addItemsWithTitles_(list(options))
    if 0 <= default_index < len(options):
        popup.selectItemAtIndex_(default_index)
    alert.setAccessoryView_(popup)
    _brand_alert_icon(alert)
    if alert.runModal() == 1000:  # NSAlertFirstButtonReturn
        return popup.titleOfSelectedItem()
    return None


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
            super().__init__("VGMCP", title=None, icon=None, quit_button=tr("종료", "Quit"))
            self.checker = EnvironmentChecker()
            # Pre-generate all status icons up front (plan §4.3) — later switches
            # are cached file lookups, never live conversions.
            from ..core import icons  # noqa: PLC0415

            icons.pregenerate(cfg.load_config().icon_size)

            self.status_item = rumps.MenuItem(tr("상태: 확인 중", "Status: checking…"),
                                              callback=self.recheck)
            self.cap_menu = rumps.MenuItem(tr("캡처", "Capture"))
            self.recent_menu = rumps.MenuItem(tr("최근 이미지", "Recent images"))
            self.backend_menu = rumps.MenuItem(tr("비전 백엔드 관리", "Manage vision backends"))
            self.autoclip_item = rumps.MenuItem(tr("자동 클립보드 복사", "Auto-copy to clipboard"),
                                                callback=self.toggle_autoclip)
            self.copyorig_item = rumps.MenuItem(
                tr("이미지 열기 시 타겟 폴더로 복사", "Copy opened images to target folder"),
                callback=self.toggle_copyorig)
            self.autostart_item = rumps.MenuItem(tr("로그인 시 자동 시작", "Start at login"),
                                                 callback=self.toggle_autostart)
            settings = rumps.MenuItem(tr("설정", "Settings"))
            settings.update([
                rumps.MenuItem(tr("타겟 폴더 설정...", "Set target folder…"),
                               callback=self.set_target_folder),
                self.backend_menu,
                rumps.MenuItem(tr("클립보드 템플릿 편집...", "Edit clipboard template…"),
                               callback=self.edit_template),
                self.autoclip_item,
                self.copyorig_item,
                self.autostart_item,
            ])
            self.menu = [
                self.status_item,
                None,
                self.cap_menu,
                rumps.MenuItem(tr("이미지 파일 열기", "Open image file"), callback=self.open_image),
                self.recent_menu,
                None,
                rumps.MenuItem(tr("마지막 이미지 분석 (테스트)", "Analyze last image (test)"),
                               callback=self.analyze_last),
                settings,
                None,
            ]
            self.refresh()
            self.timer = rumps.Timer(lambda _=None: self.refresh(), 5)
            self.timer.start()

        def _maybe_onboard(self) -> None:
            """First-run notice: permission guidance + privacy (plan §7.9, §9.1)."""
            config = cfg.load_config()
            if config.onboarding_consent_shown:
                return
            _alert(
                tr("VGMCP 시작하기", "Getting started with VGMCP"),
                tr(
                    "1) 화면 캡처에는 '화면 기록' 권한이 필요합니다: 시스템 설정 > 개인정보 보호 및 "
                    "보안 > 화면 기록에서 허용하세요.\n\n"
                    "2) 클라우드 비전 백엔드(Anthropic/OpenAI/OpenRouter/커스텀)를 쓰면 캡처 이미지가 "
                    "외부 서버로 전송됩니다. 각 백엔드 최초 사용 시 동의를 묻습니다.\n\n"
                    "3) 외부 전송 없이 쓰려면 로컬 Ollama 백엔드를 등록하세요.",
                    "1) Screen capture needs 'Screen Recording' permission: System Settings > "
                    "Privacy & Security > Screen Recording.\n\n"
                    "2) Cloud vision backends (Anthropic/OpenAI/OpenRouter/custom) send the "
                    "captured image to an external server. You'll be asked to consent on first "
                    "use of each backend.\n\n"
                    "3) To keep everything local, register the Ollama backend.",
                ),
            )
            config.onboarding_consent_shown = True
            cfg.save_config(config)

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
                self.copyorig_item.state = 1 if config.copy_original else 0
                from ..core import autostart  # noqa: PLC0415

                self.autostart_item.state = 1 if autostart.is_enabled() else 0
            except Exception as exc:  # noqa: BLE001 — never let the timer kill the app
                self.title = _ICON["red"]
                print(f"[vgmcp tray] refresh error: {exc}")

        def _refresh_status(self) -> None:
            if self.checker.check_full().ok:
                color = "green"
            elif self.checker.check_for_capture().ok:
                color = "yellow"  # capture works, provider/cred missing
            else:
                color = "red"
            self._set_status_icon(color)
            self.status_item.title = (
                tr("상태: 정상", "Status: OK") if color == "green"
                else tr("상태: 조치 필요", "Status: action needed"))

        def recheck(self, _sender=None) -> None:
            """Re-run the environment check, update the icon, and show a detailed dialog."""
            self.refresh()
            items = self.checker.detailed()
            lines = []
            for label, ok, detail in items:
                mark = "✅" if ok else "❌"
                lines.append(f"{mark} {label}" if ok else f"{mark} {label} — {detail}")
            n_fail = sum(1 for _, ok, _ in items if not ok)
            summary = (tr("모든 항목 정상", "All checks passed") if n_fail == 0
                       else tr(f"문제 {n_fail}건 — 위 항목을 확인하세요.",
                               f"{n_fail} issue(s) — see the items above."))
            _alert(tr("환경 재검사 결과", "Environment check"),
                   "\n".join(lines) + "\n\n" + tr("종합: ", "Summary: ") + summary,
                   ok=tr("닫기", "Close"))

        def _set_status_icon(self, color: str) -> None:
            from ..core import icons  # noqa: PLC0415

            size = cfg.load_config().icon_size
            try:
                path, template = icons.icon_for_status(color, size)
            except Exception:  # noqa: BLE001
                path, template = None, False
            if path is not None:
                self.template = template
                self.icon = str(path)
                self.title = None
            else:  # fallback to an emoji glyph if rasterization is unavailable
                self.icon = None
                self.title = _ICON.get(color, _ICON["gray"])

        def _refresh_capture_menu(self) -> None:
            from ..capture import get_capture_backend  # noqa: PLC0415

            items: list = []
            backend = get_capture_backend()
            if backend is not None:
                try:
                    for m in backend.list_monitors():
                        label = tr(f"모니터 {m.index} ({m.width}×{m.height})",
                                   f"Monitor {m.index} ({m.width}×{m.height})")
                        items.append(rumps.MenuItem(
                            label, callback=self._make_monitor_cb(m.index)))
                except Exception:  # noqa: BLE001
                    pass
                wins_parent = rumps.MenuItem(tr("앱 창 선택 캡처", "Capture an app window"))
                try:
                    wins = backend.list_windows()[:_MAX_WINDOWS]
                    for wi in wins:
                        label = f"{wi.app_name} — {wi.title[:30]}" if wi.title else wi.app_name
                        wins_parent.add(rumps.MenuItem(
                            label, callback=self._make_window_cb(wi.window_id)))
                except Exception:  # noqa: BLE001
                    pass
                items.append(wins_parent)
            items.append(rumps.MenuItem(tr("영역 선택 캡처 (드래그)", "Capture a region (drag)"),
                                        callback=self.cap_region))
            _set_children(self.cap_menu, items)

        def _refresh_recent_menu(self) -> None:
            config = cfg.load_config()
            items = [rumps.MenuItem(tr("타겟 폴더 열기", "Open target folder"),
                                    callback=self.open_target_folder)]
            recents = [
                rumps.MenuItem(Path(p).name, callback=self._make_recent_cb(p))
                for p in config.recent_images
            ]
            items += recents or [rumps.MenuItem(tr("(최근 이미지 없음)", "(no recent images)"),
                                                callback=None)]
            _set_children(self.recent_menu, items)

        def open_target_folder(self, _sender=None) -> None:
            import subprocess  # noqa: PLC0415

            folder = cfg.load_config().target_folder
            Path(folder).mkdir(parents=True, exist_ok=True)
            subprocess.run(["open", folder], check=False)

        def _refresh_backend_menu(self) -> None:
            config = cfg.load_config()
            items: list = []
            default_id = config.default_provider_id
            for p in config.providers:
                mark = "✓ " if p.id == default_id else "   "
                sub = rumps.MenuItem(f"{mark}{p.id} ({p.type})")
                sub.add(rumps.MenuItem(tr("기본값으로 설정", "Set as default"),
                                       callback=self._make_setdefault_cb(p.id)))
                if not p.is_local:
                    label = (tr("외부 전송 동의 해제", "Revoke external-send consent")
                             if p.consented else tr("외부 전송 동의", "Allow external send"))
                    sub.add(rumps.MenuItem(label, callback=self._make_consent_cb(p.id, not p.consented)))
                sub.add(rumps.MenuItem(tr("삭제", "Remove"),
                                       callback=self._make_removeprovider_cb(p.id)))
                items.append(sub)
            if not config.providers:
                items.append(rumps.MenuItem(tr("(등록된 provider 없음)", "(no providers registered)"),
                                            callback=None))
            items.append(rumps.MenuItem(tr("추가...", "Add…"), callback=self.add_provider))
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
                self._refresh_recent_menu()  # success is silent (toast only on failure)
            elif status == "cancelled":
                pass
            else:
                _notify(tr("캡처 실패", "Capture failed"),
                        result.get("message", status or tr("오류", "error")))

        def open_image(self, _sender=None) -> None:
            path = _pick_path(directory=False, file_types=["png", "jpg", "jpeg", "webp"])
            if not path:
                return
            result = register_image(path)
            if result.get("status") == "ok":
                self._refresh_recent_menu()  # silent on success
            else:
                _notify(tr("등록 실패", "Register failed"),
                        result.get("message", tr("오류", "error")))

        def _make_recent_cb(self, path: str):
            def cb(_=None) -> None:
                config = cfg.load_config()
                ok, _t = clipboard.copy_prompt(path, config.clipboard_template)
                if not ok:
                    _notify(tr("복사 실패", "Copy failed"), Path(path).name)
            return cb

        # ---- analysis ----------------------------------------------------- #
        def analyze_last(self, _sender=None) -> None:
            config = cfg.load_config()
            if not config.recent_images:
                _notify(tr("분석 불가", "Can't analyze"),
                        tr("최근 이미지가 없습니다. 먼저 캡처하세요.",
                           "No recent image. Capture one first."))
                return
            provider = config.effective_default()
            if provider is None:
                _notify(tr("분석 불가", "Can't analyze"),
                        tr("등록된 비전 백엔드가 없습니다. 설정에서 추가하세요.",
                           "No vision backend. Add one in Settings."))
                return
            # External-transmission consent for cloud providers (plan §7.9).
            if not provider.is_local and not provider.consented:
                if not self._confirm_consent(provider):
                    return
                config.set_consent(provider.id, True)
                cfg.save_config(config)
                self._refresh_backend_menu()
            image = config.recent_images[0]

            def worker() -> None:
                from ..server.vision_service import run_analysis  # noqa: PLC0415

                res = run_analysis(Path(image), _ANALYZE_PROMPT, None)
                text = json.dumps(res, ensure_ascii=False, indent=2)
                post_to_main(lambda: self._show_result(res, text))

            threading.Thread(target=worker, daemon=True).start()

        def _show_result(self, res: dict, text: str) -> None:
            status = res.get("status", "?")
            win = rumps.Window(
                message=tr(f"분석 결과 (status: {status}). 아래는 원본 출력(JSON)입니다.",
                           f"Analysis result (status: {status}). Raw output (JSON) below."),
                title=tr("VGMCP 분석 결과", "VGMCP analysis result"),
                default_text=text,
                ok=tr("닫기", "Close"),
                dimensions=(540, 360),
            )
            win.add_button(tr("클립보드에 복사", "Copy to clipboard"))
            _brand_alert_icon(win._alert)
            resp = win.run()
            if resp.clicked == 2:  # the extra "copy" button
                ok = clipboard.copy_to_clipboard(resp.text or text)
                if not ok:
                    _notify(tr("복사 실패", "Copy failed"),
                            tr("클립보드 복사에 실패했습니다.", "Failed to copy to clipboard."))

        def _confirm_consent(self, provider) -> bool:
            resp = _alert(
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
                ok=tr("동의하고 분석", "Agree & analyze"),
                cancel=tr("취소", "Cancel"),
            )
            return resp == 1

        # ---- settings ----------------------------------------------------- #
        def set_target_folder(self, _sender=None) -> None:
            path = _pick_path(directory=True)
            if not path:
                return
            config = cfg.load_config()
            config.target_folder = path
            cfg.save_config(config)

        def edit_template(self, _sender=None) -> None:
            config = cfg.load_config()
            current = config.clipboard_template or clipboard.DEFAULT_TEMPLATE
            new = _text_input(
                tr("클립보드 프롬프트 템플릿 ({image_path}, {filename} 사용 가능)",
                   "Clipboard prompt template ({image_path}, {filename} available)"),
                tr("템플릿 편집", "Edit template"), current)
            if new is None:
                return
            config.clipboard_template = new or None
            cfg.save_config(config)

        def toggle_autoclip(self, _sender=None) -> None:
            config = cfg.load_config()
            config.clipboard_auto = not config.clipboard_auto
            cfg.save_config(config)
            self.autoclip_item.state = 1 if config.clipboard_auto else 0

        def toggle_copyorig(self, _sender=None) -> None:
            config = cfg.load_config()
            config.copy_original = not config.copy_original
            cfg.save_config(config)
            self.copyorig_item.state = 1 if config.copy_original else 0

        def toggle_autostart(self, _sender=None) -> None:
            from ..core import autostart  # noqa: PLC0415

            if autostart.is_enabled():
                autostart.disable()
                self.autostart_item.state = 0
            else:
                autostart.enable()
                self.autostart_item.state = 1

        # ---- backend management ------------------------------------------- #
        def _make_setdefault_cb(self, pid: str):
            def cb(_=None) -> None:
                config = cfg.load_config()
                config.default_provider_id = pid
                cfg.save_config(config)
                self._refresh_backend_menu()
            return cb

        def _make_consent_cb(self, pid: str, grant: bool):
            def cb(_=None) -> None:
                config = cfg.load_config()
                config.set_consent(pid, grant)
                cfg.save_config(config)
                self._refresh_backend_menu()
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
            return cb

        def add_provider(self, _sender=None) -> None:
            title = tr("백엔드 추가", "Add backend")
            # 1) provider type: pick from a dropdown (no typing -> no typos).
            ptype = _choose_from_list(
                tr("등록할 provider 종류를 선택하세요.", "Choose a provider type."),
                title, _PROVIDER_TYPES)
            if ptype is None:
                return
            # 2) unique id: typed, since registering the same type twice needs
            #    distinct ids. The id is internal to VGMCP only — never sent out.
            config = cfg.load_config()
            prompt = tr(
                "provider 고유 id를 입력하세요. (VGMCP 내부 구분용 이름이며 외부로 전송되지 않습니다.)\n"
                "같은 종류를 여러 개 등록하려면 서로 다르게 지정하세요.",
                "Enter a unique provider id. (Internal VGMCP label only — never sent "
                "externally.)\nUse different ids to register several of the same type.")
            while True:
                pid = _text_input(prompt, title, ptype)
                if not pid:
                    return  # cancelled
                if config.get_provider(pid) is None:
                    break
                _alert(tr("중복된 id", "Duplicate id"),
                       tr(f"'{pid}' 는 이미 등록되어 있습니다. 다른 id를 입력하세요.",
                          f"'{pid}' already exists. Enter a different id."),
                       ok=tr("다시 입력", "Re-enter"))
            # 3) model: prefill + introduce a recommended model for cloud providers.
            default_model = _RECOMMENDED_MODEL.get(ptype, "")
            if ptype in _RECOMMENDED_LABEL:
                mmsg = tr(f"모델명 (추천: {_RECOMMENDED_LABEL[ptype]}). 비우면 기본값 사용.",
                          f"Model name (recommended: {_RECOMMENDED_LABEL[ptype]}). "
                          "Blank = default.")
            else:
                mmsg = tr("모델명 (비우면 기본값 사용).", "Model name (blank = default).")
            model = _text_input(mmsg, title, default_model) or ""
            base_url = None
            if ptype == "custom":
                base_url = _text_input(
                    tr("base_url (OpenAI 호환 엔드포인트)", "base_url (OpenAI-compatible endpoint)"),
                    title, "")
                if not base_url:
                    _notify(tr("추가 실패", "Add failed"),
                            tr("custom에는 base_url이 필요합니다.", "custom requires a base_url."))
                    return
            key_ref = None
            if ptype != "ollama":
                key = _text_input(tr("API 키 (비우면 환경변수 사용)", "API key (blank = use env var)"),
                                  title, "", secure=True)
                if key:
                    key_ref = f"provider:{pid}"
                    credentials.set_key(key_ref, key)
            config.add_provider(ProviderConfig(
                id=pid, type=ptype, label=pid, model=model, base_url=base_url, key_ref=key_ref))
            cfg.save_config(config)
            self._refresh_backend_menu()

    return VGMCPApp


def build_app():
    """Construct the tray app (without running the GUI loop) — used by smoke tests."""
    return _make_app_class()()


def _hide_dock_icon() -> None:
    """Run as a menu-bar-only (accessory) app: no Dock icon, no app menu.

    Accessory (not Prohibited) so modal dialogs still work.
    """
    try:
        from AppKit import NSApplication  # noqa: PLC0415

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(1)  # Accessory
        # If a Dock icon ever does appear, show our aperture (not the Python icon).
        img = _aperture_nsimage(256, template=False)
        if img is not None:
            app.setApplicationIconImage_(img)
    except Exception:  # noqa: BLE001
        pass


def run_tray() -> None:
    host.start_background()
    app = build_app()
    _hide_dock_icon()
    app._maybe_onboard()  # first-run notice (plan §7.9)
    app.run()


def _set_children(parent, children) -> None:
    # MenuItem.clear() raises if its NSMenu hasn't been created yet (empty item);
    # in that case there's nothing to clear, so just add.
    try:
        parent.clear()
    except Exception:  # noqa: BLE001 — empty submenu has no NSMenu to clear yet
        pass
    for child in children:
        parent.add(child)
