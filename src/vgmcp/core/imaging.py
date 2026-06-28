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
