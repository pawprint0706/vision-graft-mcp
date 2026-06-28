"""M7 stabilization: capture failures and chain short-circuits return structured
results instead of raising."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS capture env")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from vgmcp.capture import get_capture_backend

    b = get_capture_backend()
    if b is None or not b.check_permission():
        pytest.skip("capture backend/permission unavailable")
    from vgmcp.core import config as cfg

    c = cfg.load_config()
    c.target_folder = str(tmp_path / "shots")
    cfg.save_config(c)


def test_region_out_of_range_is_structured():
    from vgmcp.core.capture_service import perform_capture

    result = perform_capture("region", x=9_000_000, y=9_000_000, w=10, h=10)
    assert result["status"] == "error"  # CaptureError -> structured, not raised


def test_capture_and_analyze_short_circuits_on_capture_error():
    from vgmcp.server.app import capture_and_analyze

    result = capture_and_analyze(target="region")  # missing x/y/w/h
    assert result["status"] == "error"


def test_take_screenshot_window_missing_args():
    from vgmcp.core.capture_service import perform_capture

    result = perform_capture("window")  # no window_id / selector
    assert result["status"] == "error"
