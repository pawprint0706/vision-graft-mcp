"""Image preprocessing before vision API transmission (plan §7.5).

The saved original stays full-resolution; only the transmitted copy is
downscaled to `max_long_edge` (default 1568). This bounds cost/tokens without
hurting layout-level analysis (plan §7.5.2). `downscale="off"` sends as-is.
"""

from __future__ import annotations

import io
import random
from pathlib import Path

# Map Pillow format -> MIME type.
_MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def preprocess(
    image_path: Path,
    *,
    max_long_edge: int = 1568,
    downscale: str = "auto",
) -> tuple[bytes, str, int, int]:
    """Return ``(image_bytes, mime_type, width, height)`` ready for transmission.

    PNG is preferred (text/edge fidelity, plan §7.5.1). Very large images are
    re-encoded as JPEG q90 to keep payloads reasonable.
    """
    from PIL import Image  # noqa: PLC0415

    with Image.open(image_path) as img:
        img.load()
        # Normalize mode for safe re-encoding.
        if img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGB")

        w, h = img.size
        long_edge = max(w, h)

        resized = img
        if downscale != "off" and long_edge > max_long_edge:
            scale = max_long_edge / long_edge
            new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
            resized = img.resize(new_size, Image.LANCZOS)

        out_w, out_h = resized.size
        buf = io.BytesIO()
        # PNG by default; fall back to JPEG for big RGB images to cap payload.
        use_jpeg = resized.mode == "RGB" and (out_w * out_h) > 1_400_000
        if use_jpeg:
            resized.save(buf, format="JPEG", quality=90)
            mime = _MIME["JPEG"]
        else:
            if resized.mode == "L":
                resized = resized.convert("RGB") if use_jpeg else resized
            resized.save(buf, format="PNG")
            mime = _MIME["PNG"]
        return buf.getvalue(), mime, out_w, out_h


def _load_font(size: int):
    """A truetype font at the given size, falling back to Pillow's bundled font."""
    from PIL import ImageFont  # noqa: PLC0415

    for name in ("Arial Bold.ttf", "Arial.ttf", "DejaVuSans-Bold.ttf",
                 "Helvetica.ttc", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow without a size parameter
        return ImageFont.load_default()


def _draw_centered(draw, text, font, cx: int, cy: int, fill) -> None:
    """Draw ``text`` centered on (cx, cy)."""
    try:
        box = draw.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        draw.text((cx - tw // 2 - box[0], cy - th // 2 - box[1]), text,
                  fill=fill, font=font)
    except Exception:  # noqa: BLE001 — metrics are best-effort
        draw.text((8, cy), text, fill=fill, font=font)


def _jittered_center_x(draw, text, font, width: int, margin: int = 12) -> int:
    """A random horizontal center for ``text`` that keeps it fully inside ``width``.

    Shifting the code's position each time is a small anti-gaming measure: a
    text-only model can't position-guess or cache a fixed answer.
    """
    try:
        box = draw.textbbox((0, 0), text, font=font)
        half = (box[2] - box[0]) // 2
    except Exception:  # noqa: BLE001 — metrics are best-effort
        return width // 2
    low, high = half + margin, width - half - margin
    if low >= high:  # text too wide to shift — just center it
        return width // 2
    return random.randint(low, high)


def render_code_image(code: str, *, width: int = 480, height: int = 180) -> tuple[bytes, str]:
    """Return ``(png_bytes, mime)`` of a small standalone image showing ``code``.

    Used for the self_analyze capability check: only a caller that can actually
    see images can read the code back. Rendering a tiny dedicated image (instead
    of stamping the captured screenshot) avoids wasting tokens on a large image
    sent purely to deliver a code, and sidesteps layout issues on odd sizes. The
    code's horizontal position is jittered per call so it can't be position-guessed.
    """
    from PIL import Image, ImageDraw  # noqa: PLC0415

    img = Image.new("RGB", (width, height), (15, 15, 18))
    draw = ImageDraw.Draw(img)
    _draw_centered(draw, "VISION CHECK CODE", _load_font(int(height * 0.16)),
                   width // 2, int(height * 0.28), (180, 180, 190))
    code_font = _load_font(int(height * 0.42))
    cx = _jittered_center_x(draw, code, code_font, width)
    _draw_centered(draw, code, code_font, cx, int(height * 0.62), (255, 90, 90))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), _MIME["PNG"]
