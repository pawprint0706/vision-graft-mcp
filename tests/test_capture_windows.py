"""Windows capture helpers — blank-frame detection for the capture-rejection
fallback (DRM / DirectX windows that grab as solid black)."""

from __future__ import annotations

from vgmcp.capture.windows import _is_blank


class _Grab:
    def __init__(self, rgb: bytes) -> None:
        self.rgb = rgb


def test_is_blank_solid_black():
    assert _is_blank(_Grab(bytes(3 * 5000))) is True


def test_is_blank_empty():
    assert _is_blank(_Grab(b"")) is True


def test_is_blank_false_for_bright():
    assert _is_blank(_Grab(bytes([180]) * (3 * 5000))) is False


def test_is_blank_false_for_dark_theme():
    # A dark-theme UI (~#1e1e1e, avg ≈ 30) must not be mistaken for a blank grab.
    assert _is_blank(_Grab(bytes([30]) * (3 * 5000))) is False
