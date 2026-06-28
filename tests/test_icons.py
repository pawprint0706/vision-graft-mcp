"""Menu-bar status icon generation from the aperture SVG (plan §4.3)."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="NSImage rasterization (macOS)")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))


def test_generates_all_states():
    from PIL import Image

    from vgmcp.core import icons

    for state in ("normal", "yellow", "red", "gray"):
        p = icons.get_icon(state, 36)
        assert p is not None and p.exists()
        with Image.open(p) as im:
            assert im.size == (36, 36)
            assert im.mode in ("RGBA", "RGB")


def test_only_normal_is_template():
    from vgmcp.core import icons

    assert icons.is_template("normal") is True
    assert icons.is_template("yellow") is False
    assert icons.is_template("red") is False


def test_status_mapping():
    from vgmcp.core import icons

    _path, tmpl_green = icons.icon_for_status("green", 36)
    _path2, tmpl_red = icons.icon_for_status("red", 36)
    assert tmpl_green is True   # green -> normal (template)
    assert tmpl_red is False    # red -> colored


def test_size_is_configurable():
    from PIL import Image

    from vgmcp.core import icons

    p = icons.get_icon("red", 64)
    with Image.open(p) as im:
        assert im.size == (64, 64)


def test_caches_generated_file():
    from vgmcp.core import icons

    p1 = icons.get_icon("yellow", 36)
    mtime1 = p1.stat().st_mtime_ns
    p2 = icons.get_icon("yellow", 36)  # second call should reuse the cached file
    assert p2 == p1
    assert p2.stat().st_mtime_ns == mtime1
