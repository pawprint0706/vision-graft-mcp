"""External-transmission consent gate (plan §7.9)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from vgmcp.core import config as cfg
from vgmcp.core.models import ProviderConfig


def _img(p: Path) -> Path:
    Image.new("RGB", (30, 30)).save(p)
    return p


def test_cloud_requires_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from vgmcp.server.vision_service import run_analysis

    c = cfg.load_config()
    c.add_provider(ProviderConfig(id="or", type="openrouter", model="openai/gpt-4o",
                                  key_ref="provider:or"))
    cfg.save_config(c)
    res = run_analysis(_img(tmp_path / "a.png"), "p", None)
    assert res["status"] == "consent_required"
    assert res["backend"] == "or"


def test_local_needs_no_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from vgmcp.server.vision_service import run_analysis

    c = cfg.load_config()
    c.add_provider(ProviderConfig(id="local", type="ollama", model="llava"))
    cfg.save_config(c)
    # Ollama is local: no consent gate. With Ollama down this returns a
    # vision_error, NOT consent_required.
    res = run_analysis(_img(tmp_path / "a.png"), "p", None)
    assert res["status"] != "consent_required"


def test_consent_grant_allows_through(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from vgmcp.server.vision_service import run_analysis

    c = cfg.load_config()
    c.add_provider(ProviderConfig(id="or", type="openrouter", model="openai/gpt-4o",
                                  key_ref="provider:or", consented=True))
    cfg.save_config(c)
    res = run_analysis(_img(tmp_path / "a.png"), "p", None)
    # Past the consent gate; fails later (no real key) but not on consent.
    assert res["status"] != "consent_required"
