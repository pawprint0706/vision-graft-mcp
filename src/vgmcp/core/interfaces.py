"""Abstract backend interfaces (plan §6.1, §7.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import CaptureResult, MonitorInfo, VisionReportBody, WindowInfo


@runtime_checkable
class CaptureBackend(Protocol):
    """Platform capture abstraction (plan §6.1)."""

    def list_monitors(self) -> list[MonitorInfo]: ...

    def list_windows(self) -> list[WindowInfo]: ...

    def capture_monitor(self, index: int, dest: Path) -> CaptureResult: ...

    def capture_window(self, window_id: int, dest: Path) -> CaptureResult: ...

    def find_window(self, app_name: str | None, title_contains: str | None) -> int | None:
        """Resolve a window_id from a human-friendly selector (plan §6.4)."""
        ...

    def capture_region(self, x: int, y: int, w: int, h: int, dest: Path) -> CaptureResult:
        """Capture a rectangular region (pixels, primary-display top-left origin)."""
        ...

    def capture_region_interactive(self, dest: Path) -> CaptureResult | None:
        """Let the user drag-select a rectangle; None if cancelled (plan §6.5)."""
        ...

    def check_permission(self) -> bool:
        """True if screen-capture permission is granted (plan §3.2.2)."""
        ...


@runtime_checkable
class VisionBackend(Protocol):
    """Vision model call abstraction (plan §7.1).

    Implementations raise ``vgmcp.core.errors.VisionError`` on runtime failure
    and return a (possibly degraded) ``VisionReportBody`` on success.
    """

    backend_id: str

    def analyze(self, image_path: Path, prompt: str) -> VisionReportBody: ...

    def is_configured(self) -> bool: ...
