"""Windows tray behavior for the forced self-analysis setting."""

from __future__ import annotations

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
    item = next(i for i in menu.items if str(i.text).startswith("Analyze last image"))
    assert item.enabled is False
