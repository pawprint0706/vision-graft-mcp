"""Image preprocessing before vision API transmission (plan §7.5).

The saved original stays full-resolution; only the transmitted copy is
downscaled to `max_long_edge` (default 1568). This bounds cost/tokens without
hurting layout-level analysis (plan §7.5.2). `downscale="off"` sends as-is.
"""

from __future__ import annotations

import io
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


def stamp_verification_code(
    image_path: Path,
    code: str,
    *,
    max_long_edge: int = 1568,
) -> tuple[bytes, str]:
    """Return ``(png_bytes, mime)`` of the (downscaled) image with a high-contrast
    banner printing ``code`` across the top.

    Used as a capability check: only a caller that can actually see the image can
    read the code back. The original file on disk is never modified.
    """
    from PIL import Image, ImageDraw  # noqa: PLC0415

    with Image.open(image_path) as img:
        img.load()
        img = img.convert("RGB")
        w, h = img.size
        long_edge = max(w, h)
        if long_edge > max_long_edge:
            scale = max_long_edge / long_edge
            img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                             Image.LANCZOS)
            w, h = img.size

        band_h = max(36, h // 12)
        font = _load_font(int(band_h * 0.6))
        text = f"VISION CHECK CODE: {code}"

        draw = ImageDraw.Draw(img)
        # Solid banner so the code stays legible over any underlying pixels.
        draw.rectangle([0, 0, w, band_h], fill=(0, 0, 0))
        try:
            box = draw.textbbox((0, 0), text, font=font)
            tw, th = box[2] - box[0], box[3] - box[1]
            tx = max(4, (w - tw) // 2 - box[0])
            ty = max(0, (band_h - th) // 2 - box[1])
        except Exception:  # noqa: BLE001 — metrics are best-effort
            tx, ty = 8, 4
        draw.text((tx, ty), text, fill=(255, 90, 90), font=font)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), _MIME["PNG"]
