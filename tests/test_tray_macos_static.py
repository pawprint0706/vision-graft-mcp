"""Cross-platform static behavior checks for the macOS tray callbacks."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from vgmcp.core import config as cfg
from vgmcp.tray import macos


def _app(monkeypatch):
    monkeypatch.setitem(sys.modules, "rumps", SimpleNamespace(App=object))
    app_class = macos._make_app_class()
    app = app_class.__new__(app_class)
    app.refresh = lambda: None
    return app


def test_toggle_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setattr(macos, "_alert", lambda *_args, **_kwargs: 0)

    _app(monkeypatch).toggle_self_analysis()

    assert cfg.load_config().self_analysis_mode is False


def test_confirm_enables_and_second_toggle_disables(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    calls = []
    monkeypatch.setattr(macos, "_alert", lambda *args, **_kwargs: calls.append(args) or 1)
    app = _app(monkeypatch)

    app.toggle_self_analysis()
    assert cfg.load_config().self_analysis_mode is True
    app.toggle_self_analysis()

    assert cfg.load_config().self_analysis_mode is False
    assert len(calls) == 1


def test_analyze_last_returns_before_backend_in_forced_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    cfg.update_config(lambda config: setattr(config, "self_analysis_mode", True))

    _app(monkeypatch).analyze_last()


def test_refresh_updates_checkmark_and_disables_analysis(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    cfg.update_config(lambda config: setattr(config, "self_analysis_mode", True))
    app = _app(monkeypatch)
    app.refresh = app.__class__.refresh.__get__(app)
    app._refresh_status = lambda: None
    app._refresh_capture_menu = lambda: None
    app._refresh_recent_menu = lambda: None
    app._refresh_backend_menu = lambda: None
    app.self_analysis_item = SimpleNamespace(state=0)
    app.analyze_item = SimpleNamespace(set_callback=lambda callback: setattr(
        app.analyze_item, "callback", callback
    ))
    app.autoclip_item = SimpleNamespace(state=0)
    app.copyorig_item = SimpleNamespace(state=0)
    app.autostart_item = SimpleNamespace(state=0)

    app.refresh()

    assert app.self_analysis_item.state == 1
    assert app.analyze_item.callback is None
