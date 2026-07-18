"""Provider registry + default-selection logic (plan §7.3)."""

from __future__ import annotations

from vgmcp.core import config as config_module
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


def test_set_default_provider_overrides_last_used():
    """Regression: explicitly setting the default must beat a prior last-used.

    Scenario: OpenRouter was used (so last_used=openrouter), then the user picks
    Ollama as default in the tray. effective_default() prioritizes last_used, so
    set_default_provider must also pin last_used or the choice has no effect.
    """
    cfg = AppConfig()
    cfg.add_provider(_p("openrouter", "openrouter"))
    cfg.add_provider(_p("ollama", "ollama"))
    cfg.mark_used("openrouter")            # prior analysis ran on OpenRouter
    assert cfg.effective_default().id == "openrouter"

    assert cfg.set_default_provider("ollama") is True
    assert cfg.effective_default().id == "ollama"   # the explicit choice wins
    assert cfg.last_used_provider_id == "ollama"


def test_set_default_provider_unknown_id():
    cfg = AppConfig()
    cfg.add_provider(_p("a"))
    assert cfg.set_default_provider("nope") is False
    assert cfg.effective_default().id == "a"


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


def test_self_analysis_mode_defaults_off():
    assert AppConfig().self_analysis_mode is False


def test_self_analysis_mode_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    config = AppConfig(self_analysis_mode=True)
    config_module.save_config(config)
    assert config_module.load_config().self_analysis_mode is True


def test_transactional_update_preserves_self_analysis_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    config_module.save_config(AppConfig())

    config_module.update_config(
        lambda config: setattr(config, "self_analysis_mode", True)
    )
    config_module.update_config(lambda config: setattr(config, "clipboard_auto", False))

    current = config_module.load_config()
    assert current.self_analysis_mode is True
    assert current.clipboard_auto is False


# ---- recent-image existence handling (stale-path self-heal) ---------------- #
def test_prune_recent_drops_missing(tmp_path):
    real = tmp_path / "a.png"
    real.write_bytes(b"x")
    cfg = AppConfig()
    cfg.add_recent(str(tmp_path / "gone.png"))
    cfg.add_recent(str(real))
    removed = cfg.prune_recent()
    assert removed == 1
    assert cfg.recent_images == [str(real)]


def test_existing_recent_images_is_nondestructive(tmp_path):
    real = tmp_path / "a.png"
    real.write_bytes(b"x")
    cfg = AppConfig()
    cfg.add_recent(str(tmp_path / "gone.png"))
    cfg.add_recent(str(real))
    assert cfg.existing_recent_images() == [str(real)]
    # The stored list is untouched until prune_recent() is called.
    assert len(cfg.recent_images) == 2
    assert cfg.prune_recent() == 1
    assert cfg.prune_recent() == 0  # idempotent once clean
