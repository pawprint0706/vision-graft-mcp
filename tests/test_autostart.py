"""Login auto-start — macOS LaunchAgent and Windows Run key (no real side effects)."""

from __future__ import annotations

import plistlib

import pytest

from vgmcp.core import autostart
from vgmcp.core.platform import is_macos, is_windows


# --------------------------------------------------------------------------- #
# macOS — LaunchAgent plist
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not is_macos(), reason="LaunchAgent is macOS-only")
class TestLaunchAgent:
    def test_enable_writes_plist(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert autostart.is_enabled() is False
        autostart.enable(activate=False)  # don't touch the real launchd
        path = autostart.plist_path()
        assert path.exists()
        assert autostart.is_enabled() is True
        with open(path, "rb") as fh:
            data = plistlib.load(fh)
        assert data["Label"] == autostart.LABEL
        assert data["RunAtLoad"] is True
        assert data["ProgramArguments"] and data["ProgramArguments"][0].endswith("vgmcp")

    def test_disable_removes_plist(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        autostart.enable(activate=False)
        assert autostart.is_enabled() is True
        autostart.disable(activate=False)
        assert autostart.is_enabled() is False

    def test_disable_is_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        autostart.disable(activate=False)  # nothing installed — must not raise
        assert autostart.is_enabled() is False


# --------------------------------------------------------------------------- #
# Windows — Run registry key (isolated under a test-only value name)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not is_windows(), reason="Run key is Windows-only")
def test_windows_autostart_roundtrip(monkeypatch):
    # Use a throwaway value name so the user's real "VGMCP" entry is never touched.
    monkeypatch.setattr(autostart, "_WIN_VALUE", "VGMCP_PYTEST")
    assert autostart.is_enabled() is False
    try:
        location = autostart.enable()
        assert "VGMCP_PYTEST" in location
        assert autostart.is_enabled() is True
    finally:
        autostart.disable()
    assert autostart.is_enabled() is False
