"""CLI behavior that differs from MCP rich-content responses."""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastmcp.utilities.types import Image

from vgmcp import cli
from vgmcp.server import app


def test_capture_analyze_serializes_forced_mode(tmp_path, monkeypatch, capsys):
    image_path = tmp_path / "shot.png"
    monkeypatch.setenv("VGMCP_LANG", "en")
    monkeypatch.setattr(
        app,
        "take_screenshot",
        lambda **_kwargs: {"status": "ok", "path": str(image_path)},
    )
    seen = {}

    def fake_analyze(path, prompt="default prompt", backend=None):
        seen.update(path=path, prompt=prompt, backend=backend)
        return [Image(data=b"image", format="png"), "instruction"]

    monkeypatch.setattr(app, "analyze_vision", fake_analyze)
    args = SimpleNamespace(
        target="monitor", monitor=0, window_id=None, app_name=None,
        title_contains=None, x=None, y=None, w=None, h=None,
        prompt=None, backend="ignored",
    )

    exit_code = cli._cmd_capture_analyze(args)
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert result["status"] == "self_analysis_required"
    assert result["image_path"] == str(image_path)
    assert seen["prompt"] == "default prompt"
