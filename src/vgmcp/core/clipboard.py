"""Clipboard prompt supporter (plan §8).

After a capture, copy a ready-to-paste prompt (with the image path) so the user
can paste it straight into their AI coding agent.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

DEFAULT_TEMPLATE = (
    "Analyze the screenshot below. Find visual bugs — layout breakage, overlapping "
    "elements, misalignment, occlusion — and point out the likely CSS/style code areas.\n\n"
    "Image path: {image_path}\n"
    "File name: {filename}"
)


def render_prompt(
    image_path: str | Path,
    template: str | None = None,
    *,
    capture_source: str = "",
) -> str:
    """Render the clipboard prompt template (plan §8.3)."""
    path = Path(image_path)
    tmpl = template or DEFAULT_TEMPLATE
    return tmpl.format(
        image_path=str(path),
        filename=path.name,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        capture_source=capture_source,
    )


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard. Returns True on success (plan §8.4)."""
    # Prefer native NSPasteboard on macOS; fall back to pyperclip.
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString  # noqa: PLC0415

        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        return bool(pb.setString_forType_(text, NSPasteboardTypeString))
    except Exception:  # noqa: BLE001 — not macOS / AppKit unavailable
        pass
    try:
        import pyperclip  # noqa: PLC0415

        pyperclip.copy(text)
        return True
    except Exception:  # noqa: BLE001
        return False


def copy_prompt(
    image_path: str | Path,
    template: str | None = None,
    *,
    capture_source: str = "",
) -> tuple[bool, str]:
    """Render + copy in one step. Returns (ok, rendered_text)."""
    text = render_prompt(image_path, template, capture_source=capture_source)
    return copy_to_clipboard(text), text
