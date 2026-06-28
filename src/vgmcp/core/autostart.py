"""Login auto-start via a macOS LaunchAgent (plan §15 / UX).

Installs ~/Library/LaunchAgents/com.vgmcp.tray.plist with RunAtLoad so the
resident tray app starts at login. Toggled from the tray menu or the CLI.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.vgmcp.tray"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def vgmcp_executable() -> str:
    """Path to the installed `vgmcp` console script (sibling of the interpreter)."""
    candidate = Path(sys.executable).with_name("vgmcp")
    if candidate.exists():
        return str(candidate)
    import shutil  # noqa: PLC0415

    found = shutil.which("vgmcp")
    return found or str(candidate)


def is_enabled() -> bool:
    return plist_path().exists()


def _launchctl(*args: str) -> None:
    """Best-effort launchctl call; never raises (plist alone enables next login)."""
    try:
        subprocess.run(["launchctl", *args], check=False, capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def enable(*, activate: bool = True) -> Path:
    """Write the LaunchAgent plist (and load it now if activate)."""
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
    return path


def disable(*, activate: bool = True) -> None:
    """Unload and remove the LaunchAgent plist."""
    path = plist_path()
    if activate and path.exists():
        _launchctl("unload", "-w", str(path))
    path.unlink(missing_ok=True)
