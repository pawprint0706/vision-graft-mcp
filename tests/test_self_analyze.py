"""self_analyze capability gate (analyze_vision self-analysis path)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp.utilities.types import Image

from vgmcp.core.imaging import render_code_image
from vgmcp.server import vision_service as vs


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("VGMCP_LANG", "ko")


def _make_png(tmp_path: Path, size: tuple[int, int] = (200, 120)) -> Path:
    from PIL import Image as PILImage

    p = tmp_path / "shot.png"
    PILImage.new("RGB", size, (30, 60, 90)).save(p)
    return p


def test_missing_image_returns_error(tmp_path):
    res = vs.build_self_analysis(tmp_path / "nope.png", "p")
    assert res["status"] == "error"


def test_first_call_issues_challenge(tmp_path):
    src = _make_png(tmp_path)
    res = vs.build_self_analysis(src, "p")
    # [Image, instruction-text]
    assert isinstance(res, list) and len(res) == 2
    assert isinstance(res[0], Image)
    assert "CAPABILITY CHECK" in res[1]
    # A code was stored for this path.
    assert vs._VISION_CHECKS.get(str(src))


def test_correct_code_unlocks_self_analysis(tmp_path):
    src = _make_png(tmp_path)
    vs.build_self_analysis(src, "p")
    code = vs._VISION_CHECKS[str(src)]
    # Case-insensitive match.
    res = vs.build_self_analysis(src, "p", vision_check=code.lower())
    assert isinstance(res, list) and isinstance(res[0], Image)
    assert "Verification passed" in res[1]
    # One-time: the code is consumed.
    assert str(src) not in vs._VISION_CHECKS


def test_wrong_code_falls_back_to_backend(tmp_path, monkeypatch):
    src = _make_png(tmp_path)
    vs.build_self_analysis(src, "p")
    sentinel = {"status": "ok", "backend": "stub", "report": {}}
    seen = {}

    def fake_run(image_path, prompt, backend_id):
        seen["args"] = (image_path, prompt, backend_id)
        return sentinel

    monkeypatch.setattr(vs, "run_analysis", fake_run)
    res = vs.build_self_analysis(src, "p", vision_check="WRONG", backend_id="b1")
    assert res is sentinel
    assert seen["args"] == (src, "p", "b1")
    # Challenge consumed even on failure.
    assert str(src) not in vs._VISION_CHECKS


def test_missing_prior_challenge_falls_back(tmp_path, monkeypatch):
    src = _make_png(tmp_path)
    monkeypatch.setattr(vs, "run_analysis", lambda *a: {"status": "ok"})
    # vision_check supplied with no stored challenge -> cannot be trusted.
    res = vs.build_self_analysis(src, "p", vision_check="ABCDE")
    assert res["status"] == "ok"


def test_forced_mode_returns_image_without_capability_check(tmp_path):
    src = _make_png(tmp_path)
    res = vs.build_forced_self_analysis(src, "inspect layout")

    assert isinstance(res, list) and isinstance(res[0], Image)
    assert vs.forced_self_analysis_instruction() in res[1]
    assert f"이미지 경로: {src}" in res[1]
    assert "분석 요청: inspect layout" in res[1]
    assert "CAPABILITY CHECK" not in res[1]


def test_forced_instruction_uses_selected_language(tmp_path, monkeypatch):
    src = _make_png(tmp_path)
    monkeypatch.setenv("VGMCP_LANG", "en")

    res = vs.build_forced_self_analysis(src, "inspect layout")

    assert "The user has disabled vision backends" in res[1]
    assert f"Image path: {src}" in res[1]
    assert "Analysis request: inspect layout" in res[1]


def test_shared_self_analysis_builder_honors_forced_mode(tmp_path):
    from vgmcp.core import config as cfg

    src = _make_png(tmp_path)
    cfg.update_config(lambda config: setattr(config, "self_analysis_mode", True))

    res = vs.build_self_analysis(src, "inspect layout")

    assert isinstance(res, list) and isinstance(res[0], Image)
    assert "CAPABILITY CHECK" not in res[1]


def test_forced_mode_never_calls_backend(tmp_path, monkeypatch):
    import asyncio

    from vgmcp.core import config as cfg
    from vgmcp.server.app import mcp

    src = _make_png(tmp_path)
    config = cfg.load_config()
    config.self_analysis_mode = True
    cfg.save_config(config)
    monkeypatch.setattr(vs, "run_analysis", lambda *a, **k: pytest.fail("backend called"))

    async def run():
        tool = await mcp.get_tool("analyze_vision")
        return await tool.run({
            "image_path": str(src),
            "backend": "must-be-ignored",
            "self_analyze": False,
            "vision_check": "also-ignored",
        })

    result = asyncio.run(run())
    assert any(getattr(item, "type", None) == "image" for item in result.content)
    assert any(vs.forced_self_analysis_instruction() in item.text
               for item in result.content if hasattr(item, "text"))


def test_run_analysis_is_fail_closed_in_forced_mode(tmp_path, monkeypatch):
    from vgmcp.core import config as cfg

    src = _make_png(tmp_path)
    config = cfg.load_config()
    config.self_analysis_mode = True
    cfg.save_config(config)
    monkeypatch.setattr(vs, "build_backend", lambda *a: pytest.fail("backend initialized"))

    res = vs.run_analysis(src, "p", "ignored")
    assert res["status"] == "self_analysis_required"
    assert res["image_path"] == str(src)


def test_analysis_completion_does_not_disable_mode(tmp_path, monkeypatch):
    from vgmcp.core import config as cfg
    from vgmcp.core.models import ProviderConfig, VisionReportBody

    src = _make_png(tmp_path)
    config = cfg.load_config()
    config.add_provider(ProviderConfig(id="local", type="ollama"))
    cfg.save_config(config)

    class Backend:
        def analyze(self, _path, _prompt):
            cfg.update_config(
                lambda latest: setattr(latest, "self_analysis_mode", True)
            )
            return VisionReportBody(summary="ok")

    monkeypatch.setattr(vs, "build_backend", lambda *_args: Backend())
    res = vs.run_analysis(src, "p", "local")

    assert res["status"] == "ok"
    current = cfg.load_config()
    assert current.self_analysis_mode is True
    assert current.last_used_provider_id == "local"


def test_forced_mode_invalid_image_does_not_fall_back(tmp_path, monkeypatch):
    src = tmp_path / "broken.png"
    src.write_text("not an image", encoding="utf-8")
    monkeypatch.setattr(vs, "run_analysis", lambda *a: pytest.fail("backend called"))
    res = vs.build_forced_self_analysis(src, "p")
    assert res["status"] == "error"
    assert res["code"] == "image_unreadable"


def test_analyze_vision_tool_reports_missing_file(tmp_path):
    import asyncio

    from vgmcp.server.app import mcp

    async def run():
        tool = await mcp.get_tool("analyze_vision")
        res = await tool.run({"image_path": str(tmp_path / "gone.png")})
        return res.structured_content

    out = asyncio.run(run())
    assert out["status"] == "error" and out["code"] == "image_not_found"


def test_code_image_is_small_standalone_png(tmp_path):
    import io

    from PIL import Image as PILImage

    data, mime = render_code_image("446TY")
    assert mime == "image/png" and len(data) > 0
    # Dedicated small image (independent of any screenshot), so the capability
    # check stays cheap regardless of capture size.
    with PILImage.open(io.BytesIO(data)) as img:
        assert max(img.size) <= 640


def test_code_image_position_jitters():
    # Same code, rendered several times -> horizontal position varies, so the
    # bytes should not all be identical (anti position-guessing).
    outputs = {render_code_image("446TY")[0] for _ in range(8)}
    assert len(outputs) > 1


def test_long_code_falls_back_to_center(tmp_path):
    # A code too wide to shift must still render without error (centered).
    data, mime = render_code_image("WWWWWWWWWWWWWWWWWWWWWWWW")
    assert mime == "image/png" and len(data) > 0
