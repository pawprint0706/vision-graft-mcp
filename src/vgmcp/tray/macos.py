"""macOS menu-bar app (plan §4) — minimal M0 skeleton.

Runs the resident HTTP host on a background thread and shows a status item with
a colored state and a re-check action. Full menu (capture/analyze/settings)
lands in M4.
"""

from __future__ import annotations

from ..core.environment import EnvironmentChecker
from ..core.models import EnvStatus
from ..server import host

# Status icon mapping (plan §4.3).
_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⚪"}


def _state_emoji(status: EnvStatus) -> str:
    return _ICON["green"] if status.ok else _ICON["red"]


def run_tray() -> None:
    """Start host + run the rumps tray on the main thread (plan §2.4.2)."""
    import rumps  # noqa: PLC0415

    host.start_background()

    class VGMCPApp(rumps.App):
        def __init__(self) -> None:
            super().__init__("VGMCP", title=_ICON["gray"])
            self.checker = EnvironmentChecker()
            self.menu = ["환경 재검사", None]  # full menu in M4
            self.refresh(None)

        @rumps.clicked("환경 재검사")
        def refresh(self, _sender) -> None:
            status = self.checker.check_full()
            self.title = _state_emoji(status)
            if not status.ok:
                names = ", ".join(m.name for m in status.missing)
                rumps.notification("VGMCP", "환경 구성 필요", names or "누락 항목 확인")

    VGMCPApp().run()
