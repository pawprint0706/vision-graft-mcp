"""Clipboard supporter, recent-image tracking, image registration (plan §8, §4.1)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from vgmcp.core import clipboard
from vgmcp.core.config import AppConfig


def test_render_prompt_placeholders():
    text = clipboard.render_prompt("/tmp/shot.png", capture_source="monitor0")
    assert "/tmp/shot.png" in text
    assert "shot.png" in text


def test_render_prompt_custom_template():
    text = clipboard.render_prompt(
        "/a/b/c.png", "src={capture_source} file={filename}", capture_source="Safari"
    )
    assert text == "src=Safari file=c.png"


def test_add_recent_dedup_and_cap():
    cfg = AppConfig(recent_limit=3)
    for p in ["a", "b", "c", "d"]:
        cfg.add_recent(p)
    assert cfg.recent_images == ["d", "c", "b"]  # most-recent first, capped at 3
    cfg.add_recent("c")  # re-adding moves to front, no duplicate
    assert cfg.recent_images == ["c", "d", "b"]


def _write_png(p: Path, size=(120, 80)) -> Path:
    Image.new("RGB", size, (1, 2, 3)).save(p)
    return p


def test_register_image_records_recent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from vgmcp.core import capture_service, config as cfg

    img = _write_png(tmp_path / "pic.png")
    result = capture_service.register_image(str(img))
    assert result["status"] == "ok"
    assert result["width"] == 120 and result["height"] == 80
    assert cfg.load_config().recent_images == [str(img)]


def test_register_image_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from vgmcp.core import capture_service

    result = capture_service.register_image(str(tmp_path / "nope.png"))
    assert result["status"] == "error"
