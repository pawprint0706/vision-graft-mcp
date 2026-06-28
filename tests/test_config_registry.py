"""Provider registry + default-selection logic (plan §7.3)."""

from __future__ import annotations

from vgmcp.core.config import AppConfig
from vgmcp.core.models import ProviderConfig


def _p(pid: str, ptype: str = "anthropic") -> ProviderConfig:
    return ProviderConfig(id=pid, type=ptype, label=pid, model="m")


def test_first_registered_becomes_default():
    cfg = AppConfig()
    cfg.add_provider(_p("a"))
    cfg.add_provider(_p("b"))
    # First registered is the default until something is used (plan §7.3 rule 2).
    assert cfg.default_provider_id == "a"
    assert cfg.effective_default().id == "a"


def test_last_used_overrides_default():
    cfg = AppConfig()
    cfg.add_provider(_p("a"))
    cfg.add_provider(_p("b"))
    cfg.mark_used("b")  # plan §7.3 rule 3
    assert cfg.effective_default().id == "b"
    assert cfg.last_used_provider_id == "b"


def test_remove_default_reassigns():
    cfg = AppConfig()
    cfg.add_provider(_p("a"))
    cfg.add_provider(_p("b"))
    cfg.mark_used("a")
    cfg.remove_provider("a")
    # Default falls back to a remaining provider, last_used cleared.
    assert cfg.default_provider_id == "b"
    assert cfg.last_used_provider_id is None
    assert cfg.effective_default().id == "b"


def test_ollama_is_local():
    cfg = AppConfig()
    cfg.add_provider(_p("local", "ollama"))
    assert cfg.effective_default().is_local is True
