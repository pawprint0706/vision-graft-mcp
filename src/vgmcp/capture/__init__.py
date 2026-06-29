"""Capture backends (plan §6).

`get_capture_backend()` returns the platform implementation, or None when the
native capture stack isn't available (EnvironmentChecker then reports the gap).
"""

from __future__ import annotations

from ..core.interfaces import CaptureBackend
from ..core.platform import is_macos, is_windows, module_available

_cached: CaptureBackend | None = None
_resolved = False


def get_capture_backend() -> CaptureBackend | None:
    global _cached, _resolved
    if _resolved:
        return _cached
    _resolved = True
    if is_macos() and module_available("ScreenCaptureKit"):
        from .macos import MacOSCaptureBackend  # noqa: PLC0415

        _cached = MacOSCaptureBackend()
    elif is_windows() and module_available("mss") and module_available("win32gui"):
        from .windows import WindowsCaptureBackend  # noqa: PLC0415

        _cached = WindowsCaptureBackend()
    else:
        _cached = None
    return _cached
