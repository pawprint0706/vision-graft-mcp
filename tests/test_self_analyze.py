"""self_analyze capability gate (analyze_vision self-analysis path)."""

from __future__ import annotations

from pathlib import Path

from fastmcp.utilities.types import Image

from vgmcp.core.imaging import render_code_image
from vgmcp.server import vision_service as vs


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
