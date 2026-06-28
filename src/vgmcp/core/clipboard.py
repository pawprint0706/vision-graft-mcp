"""Clipboard prompt supporter (plan §8).

After a capture, copy a ready-to-paste prompt (with the image path) so the user
can paste it straight into their AI coding agent.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

DEFAULT_TEMPLATE = (
    "아래 스크린샷을 분석해 줘. UI 레이아웃 깨짐, 요소 겹침, 정렬 불량, 가려짐 등 "
    "시각적 버그를 찾고, 원인이 될 만한 CSS/스타일 코드 영역을 짚어 줘.\n\n"
    "이미지 경로: {image_path}\n"
    "파일명: {filename}"
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
