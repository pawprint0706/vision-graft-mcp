"""EnvironmentChecker config freshness + detailed report (plan §3.2)."""

from __future__ import annotations

from vgmcp.core import config as cfg
from vgmcp.core.environment import EnvironmentChecker
from vgmcp.core.models import ProviderConfig


def test_checker_reflects_config_changes_without_reinstantiation(tmp_path, monkeypatch):
    """Regression: a long-lived checker (like the tray's) must see live config edits."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    chk = EnvironmentChecker()

    # No provider -> credential check fails.
    before = EnvironmentChecker().check_for_vision()
    assert before.ok is False

    c = cfg.load_config()
    c.add_provider(ProviderConfig(id="ollama", type="ollama", model="llava"))
    cfg.save_config(c)

    # Same instance must now pass (config reloaded, not cached).
    after = chk.check_for_vision()
    assert after.ok is True


def test_pinned_config_is_not_reloaded(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    pinned = cfg.AppConfig()  # empty, no providers
    chk = EnvironmentChecker(pinned)

    # Write a provider to disk; the pinned checker should ignore it.
    c = cfg.load_config()
    c.add_provider(ProviderConfig(id="ollama", type="ollama", model="llava"))
    cfg.save_config(c)

    assert chk.check_for_vision().ok is False  # still using pinned empty config


def test_detailed_report_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    report = EnvironmentChecker().detailed()
    labels = [label for label, _ok, _detail in report]
    assert "Python ≥ 3.11" in labels
    assert "비전 백엔드 자격증명" in labels
    for _label, ok, detail in report:
        assert isinstance(ok, bool)
        assert detail  # non-empty ("정상" or a reason)
