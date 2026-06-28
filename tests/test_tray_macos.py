"""Tray app construction (plan §4). GUI loop is not started; we only verify the
menu structure builds and dynamic submenus populate."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    pytest.importorskip("rumps")
    from vgmcp.capture import get_capture_backend

    backend = get_capture_backend()
    if backend is None or not backend.check_permission():
        pytest.skip("capture backend/permission unavailable")

    from vgmcp.core import config as cfg
    from vgmcp.core.models import ProviderConfig

    c = cfg.load_config()
    c.add_provider(ProviderConfig(id="ollama", type="ollama", model="llava"))
    cfg.save_config(c)

    from vgmcp.tray.macos import build_app

    a = build_app()
    a.stop_timer()
    yield a


def test_top_menu(app):
    keys = list(app.menu.keys())
    assert "캡처" in keys
    assert "설정" in keys
    assert "최근 이미지" in keys
    assert "마지막 이미지 분석" in keys


def test_capture_submenu(app):
    caps = list(app.menu["캡처"].keys())
    assert any("모니터" in k for k in caps)
    assert "앱 창 선택 캡처" in caps
    assert "영역 선택 캡처 (드래그)" in caps
    assert "이미지 파일 열기..." in caps


def test_backend_submenu_reflects_default(app):
    keys = list(app.backend_menu.keys())
    assert any(k.startswith("✓") and "ollama" in k for k in keys)
    assert "추가..." in keys


def test_status_green_when_configured(app):
    # ollama provider + capture available -> environment ok -> green
    assert app.title == "🟢"
