"""macOS ScreenCaptureKit capture (plan §6.2, M2).

Skipped unless running on macOS with the capture backend available and Screen
Recording permission granted (these tests actually capture the screen).
"""

from __future__ import annotations

import sys

import pytest

from vgmcp.capture import get_capture_backend

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


@pytest.fixture
def backend():
    b = get_capture_backend()
    if b is None:
        pytest.skip("macOS capture backend unavailable (pyobjc not installed)")
    if not b.check_permission():
        pytest.skip("Screen Recording permission not granted")
    return b


def test_list_monitors(backend):
    monitors = backend.list_monitors()
    assert len(monitors) >= 1
    m = monitors[0]
    assert m.width > 0 and m.height > 0
    assert m.dpi_scale >= 1.0
    assert any(x.primary for x in monitors)


def test_capture_monitor(backend, tmp_path):
    result = backend.capture_monitor(0, tmp_path)
    from pathlib import Path

    from PIL import Image

    p = Path(result.path)
    assert p.exists()
    assert result.status == "ok"
    with Image.open(p) as im:
        assert im.size == (result.width, result.height)
    assert result.source == "monitor0"


def test_capture_monitor_bad_index(backend, tmp_path):
    from vgmcp.core.errors import CaptureError

    with pytest.raises(CaptureError):
        backend.capture_monitor(999, tmp_path)


def test_capture_region(backend, tmp_path):
    from pathlib import Path

    from PIL import Image

    result = backend.capture_region(50, 50, 320, 200, tmp_path)
    assert result.status == "ok"
    assert (result.width, result.height) == (320, 200)
    p = Path(result.path)
    assert p.exists()
    with Image.open(p) as im:
        assert im.size == (320, 200)
    # The intermediate full-screen capture must be cleaned up.
    assert [f.name for f in tmp_path.iterdir()] == [p.name]


def test_capture_region_bad_size(backend, tmp_path):
    from vgmcp.core.errors import CaptureError

    with pytest.raises(CaptureError):
        backend.capture_region(0, 0, 0, 100, tmp_path)
