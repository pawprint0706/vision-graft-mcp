"""Language selection for UI strings (core.i18n)."""

from __future__ import annotations

from vgmcp.core import i18n


def test_explicit_korean(monkeypatch):
    monkeypatch.setenv("VGMCP_LANG", "ko")
    assert i18n.current_lang() == "ko"
    assert i18n.tr("안녕", "hello") == "안녕"


def test_explicit_english(monkeypatch):
    monkeypatch.setenv("VGMCP_LANG", "en")
    assert i18n.current_lang() == "en"
    assert i18n.tr("안녕", "hello") == "hello"


def test_posix_locale_korean(monkeypatch):
    # No explicit override; fall back to POSIX locale env (Foundation may also be
    # consulted first on macOS, so only assert the env-based path when override set).
    monkeypatch.delenv("VGMCP_LANG", raising=False)
    monkeypatch.setattr(i18n, "_detected", None)
    monkeypatch.setattr(i18n, "_detect", lambda: "ko")
    assert i18n.current_lang() == "ko"


def test_invalid_override_ignored(monkeypatch):
    monkeypatch.setenv("VGMCP_LANG", "zz")
    monkeypatch.setattr(i18n, "_detected", None)
    monkeypatch.setattr(i18n, "_detect", lambda: "en")
    assert i18n.current_lang() == "en"
