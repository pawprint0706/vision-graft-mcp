"""Login auto-start LaunchAgent (no real launchctl side effects)."""

from __future__ import annotations

import plistlib

from vgmcp.core import autostart


def test_enable_writes_plist(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert autostart.is_enabled() is False
    path = autostart.enable(activate=False)  # don't touch the real launchd
    assert path.exists()
    assert autostart.is_enabled() is True
    with open(path, "rb") as fh:
        data = plistlib.load(fh)
    assert data["Label"] == autostart.LABEL
    assert data["RunAtLoad"] is True
    assert data["ProgramArguments"] and data["ProgramArguments"][0].endswith("vgmcp")


def test_disable_removes_plist(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    autostart.enable(activate=False)
    assert autostart.is_enabled() is True
    autostart.disable(activate=False)
    assert autostart.is_enabled() is False


def test_disable_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    autostart.disable(activate=False)  # nothing installed — must not raise
    assert autostart.is_enabled() is False
