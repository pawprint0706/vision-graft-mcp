"""Vision report parsing, preprocessing, and the staged fallback (plan §7.5/§7.7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vgmcp.core import config as cfg
from vgmcp.core.errors import SelfAnalysisRequired
from vgmcp.core.imaging import preprocess
from vgmcp.core.models import ProviderConfig
from vgmcp.vision import report as report_mod
from vgmcp.vision.base import BaseVisionBackend


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))


# ---- report parsing ------------------------------------------------------- #
def test_parse_direct_json():
    r = report_mod.try_parse('{"summary": "ok", "issues": []}')
    assert r is not None and r.summary == "ok" and not r.parse_degraded


def test_parse_fenced_json():
    raw = "분석 결과입니다:\n```json\n{\"summary\": \"s\", \"issues\": "\
          "[{\"severity\": \"high\", \"description\": \"d\"}]}\n```\n끝."
    r = report_mod.try_parse(raw)
    assert r is not None
    assert r.issues[0].severity == "high"
    assert r.raw_text == raw


def test_parse_invalid_returns_none():
    assert report_mod.try_parse("그냥 평범한 설명, JSON 아님") is None


def test_degraded_preserves_raw():
    r = report_mod.degraded("첫 줄 요약\n둘째 줄")
    assert r.parse_degraded is True
    assert r.summary == "첫 줄 요약"
    assert r.raw_text == "첫 줄 요약\n둘째 줄"


def test_bad_severity_coerced():
    r = report_mod.try_parse('{"summary":"s","issues":[{"severity":"critical","description":"d"}]}')
    assert r.issues[0].severity == "medium"


# ---- preprocessing -------------------------------------------------------- #
def _make_png(tmp_path: Path, size: tuple[int, int]) -> Path:
    from PIL import Image

    p = tmp_path / "shot.png"
    Image.new("RGB", size, (123, 200, 50)).save(p)
    return p


def test_preprocess_downscales_long_edge(tmp_path):
    src = _make_png(tmp_path, (4000, 1000))
    data, mime, w, h = preprocess(src, max_long_edge=1568, downscale="auto")
    assert w == 1568 and h == 392
    assert mime in ("image/png", "image/jpeg")
    assert len(data) > 0


def test_preprocess_off_keeps_size(tmp_path):
    src = _make_png(tmp_path, (2000, 100))
    _data, _mime, w, h = preprocess(src, max_long_edge=1568, downscale="off")
    assert (w, h) == (2000, 100)


# ---- staged fallback in BaseVisionBackend --------------------------------- #
class _FakeBackend(BaseVisionBackend):
    def __init__(self, replies):
        super().__init__(ProviderConfig(id="fake", type="ollama", model="x"))
        self._replies = list(replies)
        self.calls = 0

    def is_configured(self) -> bool:
        return True

    def _complete(self, image_bytes, mime, prompt):
        self.calls += 1
        return self._replies.pop(0)


def test_corrective_retry_recovers(tmp_path, monkeypatch):
    # First reply is prose (unparseable), retry returns valid JSON.
    src = _make_png(tmp_path, (10, 10))
    be = _FakeBackend(["설명만 있는 응답", '{"summary":"recovered","issues":[]}'])
    report = be.analyze(src, "prompt")
    assert be.calls == 2
    assert report.summary == "recovered"
    assert report.parse_degraded is False


def test_falls_back_to_degraded(tmp_path):
    src = _make_png(tmp_path, (10, 10))
    be = _FakeBackend(["prose one", "prose two"])
    report = be.analyze(src, "prompt")
    assert be.calls == 2
    assert report.parse_degraded is True
    assert report.raw_text == "prose two"


def test_corrective_retry_is_blocked_when_mode_turns_on(tmp_path):
    src = _make_png(tmp_path, (10, 10))

    class _EnableModeBackend(_FakeBackend):
        def _complete(self, image_bytes, mime, prompt):
            self.calls += 1
            cfg.update_config(lambda current: setattr(current, "self_analysis_mode", True))
            return "unparseable"

    be = _EnableModeBackend([])
    with pytest.raises(SelfAnalysisRequired):
        be.analyze(src, "prompt")
    assert be.calls == 1
