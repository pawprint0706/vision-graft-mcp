"""macOS capture backend — ScreenCaptureKit (plan §2.4.3, §6.2).

Implemented in milestones M2 (monitor) and M3 (window). M0 ships the structure
and a permission probe; the actual capture methods raise until those milestones.

Why ScreenCaptureKit: CGWindowListCreateImage is obsoleted in macOS 15.0 and
deprecated capture APIs escalate Sequoia's permission nag (plan §9.1).
"""

from __future__ import annotations

from pathlib import Path

from ..core.errors import CaptureError
from ..core.models import CaptureResult, MonitorInfo, WindowInfo


class MacOSCaptureBackend:
    """ScreenCaptureKit-based capture (plan §6.2)."""

    def list_monitors(self) -> list[MonitorInfo]:  # noqa: D102 — M2
        raise NotImplementedError("list_monitors lands in M2")

    def list_windows(self) -> list[WindowInfo]:  # noqa: D102 — M3
        raise NotImplementedError("list_windows lands in M3")

    def capture_monitor(self, index: int, dest: Path) -> CaptureResult:  # noqa: D102 — M2
        raise NotImplementedError("capture_monitor lands in M2")

    def capture_window(self, window_id: int, dest: Path) -> CaptureResult:  # noqa: D102 — M3
        raise NotImplementedError("capture_window lands in M3")

    def check_permission(self) -> bool:
        """Probe Screen Recording permission (plan §3.2.2).

        Uses SCShareableContent: if the system denies capture access the call
        fails or returns no displays. (CGPreflightScreenCaptureAccess is
        deprecated in 15.1 — plan §9.1 — so we don't rely on it.)
        """
        try:
            import threading  # noqa: PLC0415

            import ScreenCaptureKit as SCK  # noqa: PLC0415, N813

            result: dict[str, object] = {}
            done = threading.Event()

            def handler(content, error):  # SCShareableContent completion
                result["content"] = content
                result["error"] = error
                done.set()

            SCK.SCShareableContent.getShareableContentWithCompletionHandler_(handler)
            if not done.wait(timeout=3.0):
                return False
            content = result.get("content")
            if result.get("error") is not None or content is None:
                return False
            displays = content.displays()
            return displays is not None and len(displays) > 0
        except Exception as exc:  # noqa: BLE001
            raise CaptureError(f"permission probe failed: {exc}") from exc
