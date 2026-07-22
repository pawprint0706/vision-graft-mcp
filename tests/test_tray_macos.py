"""Tray app construction (plan §4). GUI loop is not started; we only verify the
menu structure builds and dynamic submenus populate."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("VGMCP_LANG", "ko")  # deterministic labels for assertions
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
    assert "모니터 캡쳐" in keys
    assert "앱 창 선택 캡쳐" in keys
    assert "영역 선택 캡쳐 (드래그)" in keys
    assert "이미지 파일 열기" in keys
    assert "설정" in keys
    assert "최근 이미지" in keys
    assert "마지막 이미지 분석 (테스트)" in keys


def test_status_item_is_first(app):
    keys = list(app.menu.keys())
    status_key = next(k for k in keys if k.startswith("상태"))
    assert keys.index(status_key) < keys.index("모니터 캡쳐")
    assert app.status_item.title.startswith("상태:")


def test_recheck_removed_from_settings(app):
    # '환경 재검사' moved out; recheck now lives on the top status item.
    assert "환경 재검사" not in list(app.menu["설정"].keys())


def test_self_analysis_precedes_backend_setting(app):
    keys = list(app.menu["설정"].keys())
    assert keys.index("셀프 분석 모드 사용") < keys.index("비전 백엔드 관리")


def test_capture_submenus(app):
    assert any("모니터" in key for key in app.menu["모니터 캡쳐"].keys())
    assert list(app.menu["앱 창 선택 캡쳐"].keys())


def test_recent_menu_keeps_target_folder_action(app):
    assert list(app.menu["최근 이미지"].keys())[0] == "타겟 폴더 열기"


def test_menu_order(app):
    keys = [k for k in app.menu.keys() if not k.startswith("Separator")]
    def idx(prefix):
        return next(i for i, k in enumerate(keys) if k.startswith(prefix))

    assert idx("상태") < idx("모니터 캡쳐") < idx("앱 창 선택 캡쳐")
    assert idx("앱 창 선택 캡쳐") < idx("영역 선택 캡쳐") < idx("이미지 파일 열기")
    assert idx("이미지 파일 열기") < idx("최근 이미지") < idx("마지막 이미지 분석")
    assert idx("마지막 이미지 분석") < idx("설정") < idx("종료")


def test_backend_submenu_reflects_default(app):
    keys = list(app.backend_menu.keys())
    assert any(k.startswith("✓") and "ollama" in k for k in keys)
    assert "추가..." in keys


def test_status_uses_svg_icon(app):
    # ollama provider + capture available -> environment ok -> normal (template) icon
    from pathlib import Path

    assert app.icon is not None
    assert Path(app.icon).exists()
    assert "camera_normal" in Path(app.icon).name
    assert app.template is True  # normal icon is a template (auto light/dark)
    assert app.title is None
