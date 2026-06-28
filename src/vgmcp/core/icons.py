"""Menu-bar status icons generated from the aperture SVG (plan §4.3).

Three states, recolored from a single line-art SVG and rasterized to PNG with
NSImage (no extra dependencies):

  * normal  — black "template" image; macOS renders it black or white according
              to light/dark menu bar automatically.
  * yellow  — amber lines (partial: capture works, a backend/credential missing).
  * red     — red lines (blocking: core dependency/permission missing).

`size` is the render resolution; the menu bar displays at ~20pt, so a larger
size just means crisper retina output.
"""

from __future__ import annotations

from pathlib import Path

from .config import config_dir

# State -> stroke color. "normal" stays black so it can be a template image.
_COLORS = {
    "normal": "#000000",
    "yellow": "#F5A623",
    "red": "#FF3B30",
    "gray": "#8E8E93",
}

DEFAULT_SIZE = 36  # render px; displayed at the menu bar's ~20pt (retina-crisp)

STATES = ("normal", "yellow", "red", "gray")

# Map EnvironmentChecker status colors (plan §4.3) to icon states.
STATUS_TO_STATE = {"green": "normal", "yellow": "yellow", "red": "red", "gray": "gray"}


def is_template(state: str) -> bool:
    """Only the normal (black) icon is a template (auto light/dark)."""
    return state == "normal"


def _base_svg() -> str:
    return (Path(__file__).resolve().parent.parent / "assets" / "aperture.svg").read_text(
        encoding="utf-8"
    )


def _icons_dir() -> Path:
    d = config_dir() / "icons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rasterize(svg_text: str, size: int, dest: Path) -> bool:
    """Render SVG text to a PNG at size×size via NSImage. Returns success."""
    try:
        from AppKit import (  # noqa: PLC0415
            NSBitmapImageRep,
            NSCompositingOperationSourceOver,
            NSGraphicsContext,
            NSImage,
            NSMakeRect,
            NSMakeSize,
            NSZeroRect,
        )
        from Foundation import NSData  # noqa: PLC0415
    except ImportError:
        return False

    raw = svg_text.encode("utf-8")
    data = NSData.dataWithBytes_length_(raw, len(raw))
    img = NSImage.alloc().initWithData_(data)
    if img is None:
        return False
    img.setSize_(NSMakeSize(size, size))

    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(  # noqa: E501
        None, size, size, 8, 4, True, False, "NSCalibratedRGBColorSpace", 0, 0
    )
    if rep is None:
        return False
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    img.drawInRect_fromRect_operation_fraction_(
        NSMakeRect(0, 0, size, size), NSZeroRect, NSCompositingOperationSourceOver, 1.0
    )
    NSGraphicsContext.restoreGraphicsState()

    png = rep.representationUsingType_properties_(4, {})  # 4 = NSBitmapImageFileTypePNG
    if png is None:
        return False
    return bool(png.writeToFile_atomically_(str(dest), True))


def get_icon(state: str, size: int = DEFAULT_SIZE) -> Path | None:
    """Return a PNG path for the given state, generating/caching as needed."""
    if state not in _COLORS:
        state = "normal"
    dest = _icons_dir() / f"aperture_{state}_{size}.png"
    if dest.exists():
        return dest
    svg = _base_svg().replace('stroke="#000000"', f'stroke="{_COLORS[state]}"')
    return dest if _rasterize(svg, size, dest) else None


def icon_for_status(status_color: str, size: int = DEFAULT_SIZE) -> tuple[Path | None, bool]:
    """Map a status color to (icon_path, is_template)."""
    state = STATUS_TO_STATE.get(status_color, "normal")
    return get_icon(state, size), is_template(state)


def pregenerate(size: int = DEFAULT_SIZE) -> dict[str, Path | None]:
    """Generate all state icons once up front (called at app launch) so switching
    states later is a cached file lookup, never a live conversion."""
    return {state: get_icon(state, size) for state in STATES}
