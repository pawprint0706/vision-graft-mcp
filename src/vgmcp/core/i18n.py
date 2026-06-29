"""Tiny localization: Korean if the OS prefers Korean, otherwise English.

Usage:  from .i18n import tr;  tr("한국어 문구", "English text")

Language resolution order:
  1. VGMCP_LANG env var ("ko" | "en") — explicit override (also used by tests)
  2. macOS preferred language (Foundation.NSLocale.preferredLanguages)
  3. POSIX locale env vars (LANGUAGE / LC_ALL / LC_MESSAGES / LANG)
  4. fallback: English
"""

from __future__ import annotations

import os

_detected: str | None = None


def _detect() -> str:
    try:
        from Foundation import NSLocale  # noqa: PLC0415

        langs = NSLocale.preferredLanguages()
        if langs and len(langs):
            return "ko" if str(langs[0]).lower().startswith("ko") else "en"
    except Exception:  # noqa: BLE001 — not macOS / Foundation unavailable
        pass
    import sys  # noqa: PLC0415

    if sys.platform.startswith("win"):
        # POSIX locale env vars are usually unset on Windows; ask the OS for the
        # user's UI language. LANG_KOREAN primary id == 0x12.
        try:
            import ctypes  # noqa: PLC0415

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "ko" if (langid & 0x3FF) == 0x12 else "en"
        except Exception:  # noqa: BLE001
            pass
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            return "ko" if val.lower().startswith("ko") else "en"
    return "en"


def current_lang() -> str:
    override = os.environ.get("VGMCP_LANG")
    if override in ("ko", "en"):
        return override
    global _detected
    if _detected is None:
        _detected = _detect()
    return _detected


def tr(ko: str, en: str) -> str:
    """Return `ko` when the UI language is Korean, else `en`."""
    return ko if current_lang() == "ko" else en
