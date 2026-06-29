"""Login auto-start (plan §15 / UX).

macOS:   ~/Library/LaunchAgents/com.vgmcp.tray.plist with RunAtLoad.
Windows: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run "VGMCP" value.

Toggled from the tray menu or the `vgmcp autostart` CLI subcommand. The public
API (is_enabled / enable / disable / location) is platform-neutral.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .platform import is_windows

LABEL = "com.vgmcp.tray"
_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_WIN_VALUE = "VGMCP"


def vgmcp_executable() -> str:
    """Path to the installed `vgmcp` console script (sibling of the interpreter)."""
    name = "vgmcp.exe" if is_windows() else "vgmcp"
    candidate = Path(sys.executable).with_name(name)
    if candidate.exists():
        return str(candidate)
    import shutil  # noqa: PLC0415

    found = shutil.which("vgmcp")
    return found or str(candidate)


# --------------------------------------------------------------------------- #
# macOS — LaunchAgent
# --------------------------------------------------------------------------- #
def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _launchctl(*args: str) -> None:
    """Best-effort launchctl call; never raises (plist alone enables next login)."""
    import subprocess  # noqa: PLC0415

    try:
        subprocess.run(["launchctl", *args], check=False, capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def _mac_is_enabled() -> bool:
    return plist_path().exists()


def _mac_enable(activate: bool) -> str:
    import plistlib  # noqa: PLC0415

    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [vgmcp_executable()],
        "RunAtLoad": True,
        "ProcessType": "Interactive",
    }
    with open(path, "wb") as fh:
        plistlib.dump(payload, fh)
    if activate:
        _launchctl("load", "-w", str(path))
    return str(path)


def _mac_disable(activate: bool) -> None:
    path = plist_path()
    if activate and path.exists():
        _launchctl("unload", "-w", str(path))
    path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Windows — Run registry key
# --------------------------------------------------------------------------- #
def _win_command() -> str:
    """Launch command for autostart. Prefer pythonw.exe -m vgmcp so no console
    window flashes at login; fall back to the vgmcp.exe console script."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if pythonw.exists():
        return f'"{pythonw}" -m vgmcp'
    return f'"{vgmcp_executable()}"'


def _win_is_enabled() -> bool:
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
            winreg.QueryValueEx(key, _WIN_VALUE)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _win_enable() -> str:
    import winreg  # noqa: PLC0415

    command = _win_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
        winreg.SetValueEx(key, _WIN_VALUE, 0, winreg.REG_SZ, command)
    return f"HKCU\\{_WIN_RUN_KEY}\\{_WIN_VALUE}"


def _win_disable() -> None:
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _WIN_VALUE)
    except FileNotFoundError:
        pass
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Platform-neutral public API
# --------------------------------------------------------------------------- #
def is_enabled() -> bool:
    if is_windows():
        return _win_is_enabled()
    return _mac_is_enabled()


def enable(*, activate: bool = True) -> str:
    """Register login auto-start. Returns the location string (path / registry)."""
    if is_windows():
        return _win_enable()
    return _mac_enable(activate)


def disable(*, activate: bool = True) -> None:
    if is_windows():
        _win_disable()
        return
    _mac_disable(activate)


def location() -> str:
    """Where the autostart entry lives, for display/status."""
    if is_windows():
        return f"HKCU\\{_WIN_RUN_KEY}\\{_WIN_VALUE}"
    return str(plist_path())
