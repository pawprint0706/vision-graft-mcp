"""Windows tray behavior for the forced self-analysis setting."""

from __future__ import annotations

from pathlib import Path

import pytest

from vgmcp.core import config as cfg
from vgmcp.core.environment import EnvironmentChecker
from vgmcp.tray import windows

pystray = pytest.importorskip("pystray")


def _app():
    app = windows.WindowsTrayApp.__new__(windows.WindowsTrayApp)
    app._pystray = pystray
    app.checker = EnvironmentChecker()
    app._refresh = lambda: None
    return app


def test_self_analysis_precedes_backend_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("VGMCP_LANG", "en")
    menu = _app()._settings_menu()
    labels = [str(item.text) for item in menu.items]
    assert labels.index("Use self-analysis mode") < labels.index("Manage vision backends")


def test_enabling_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("VGMCP_LANG", "ko")
    seen = {}

    def reject(title, message):
        seen["dialog"] = (title, message)
        return False

    monkeypatch.setattr(windows, "_confirm", reject)
    _app()._on_toggle_self_analysis()

    assert cfg.load_config().self_analysis_mode is False
    assert "셀프 분석 모드는 비전 백엔드 요청 없이" in seen["dialog"][1]


def test_confirm_enables_and_second_toggle_disables(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    calls = []
    monkeypatch.setattr(windows, "_confirm", lambda *a: calls.append(a) or True)
    app = _app()

    app._on_toggle_self_analysis()
    assert cfg.load_config().self_analysis_mode is True
    app._on_toggle_self_analysis()
    assert cfg.load_config().self_analysis_mode is False
    assert len(calls) == 1


def test_analyze_last_is_disabled_in_self_analysis_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("VGMCP_LANG", "en")
    config = cfg.load_config()
    config.self_analysis_mode = True
    cfg.save_config(config)

    menu = _app()._build_menu()
    item = next(i for i in menu.items if str(i.text) == "Analyze last image (test)")
    assert item.enabled is False


def test_top_menu_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("VGMCP_LANG", "ko")

    labels = ["---" if item is pystray.Menu.SEPARATOR else str(item.text)
              for item in _app()._build_menu().items]

    assert labels == [
        "상태: 조치 필요",
        "---",
        "모니터 캡쳐",
        "앱 창 선택 캡쳐",
        "영역 선택 캡쳐 (드래그)",
        "이미지 파일 열기",
        "---",
        "최근 이미지",
        "마지막 이미지 분석 (테스트)",
        "---",
        "설정",
        "종료",
    ]


def test_recent_menu_keeps_target_folder_action(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("VGMCP_LANG", "ko")

    labels = [str(item.text) for item in _app()._recent_menu().items]

    assert labels[0] == "타겟 폴더 열기"


def test_status_icon_is_rendered_from_shared_svg(tmp_path, monkeypatch):
    assert windows._icon_path().name == "camera.svg"
    svg = tmp_path / "icon.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<rect width="10" height="10" fill="#000000"/></svg>',
        encoding="utf-8",
    )
    monkeypatch.setattr(windows, "_icon_path", lambda: Path(svg))
    monkeypatch.setattr(windows, "_taskbar_uses_light_theme", lambda: False)
    windows._ICON_CACHE.clear()

    image = windows._status_image("green", 24)

    assert image.size == (24, 24)
    assert image.getpixel((12, 12)) == (255, 255, 255, 255)
