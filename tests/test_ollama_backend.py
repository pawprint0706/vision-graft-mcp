"""Ollama backend request shape + empty-content handling (reasoning models)."""

from __future__ import annotations

import httpx
import pytest

from vgmcp.core.errors import VisionError, VisionErrorCode
from vgmcp.core.models import ProviderConfig
from vgmcp.vision import ollama_backend


class _Resp:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("POST", "http://x"), response=self
            )

    def json(self):
        return self._payload


def _backend():
    return ollama_backend.OllamaBackend(
        ProviderConfig(id="ollama", type="ollama", model="qwen3-vl:4b"),
        host="http://localhost:11434",
    )


def test_request_disables_thinking_and_uses_content(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["body"] = json
        return _Resp({"message": {"content": '{"summary":"ok","issues":[]}'}})

    monkeypatch.setattr(ollama_backend.httpx, "post", fake_post)
    out = _backend()._complete(b"img", "image/png", "prompt")

    assert captured["body"]["think"] is False      # reasoning off (qwen3-vl fix)
    assert captured["body"]["format"] == "json"
    assert out == '{"summary":"ok","issues":[]}'


def test_falls_back_to_thinking_when_content_empty(monkeypatch):
    # Reasoning model that still routed text to `thinking` despite think=false.
    def fake_post(url, json=None, timeout=None):
        return _Resp({"message": {"content": "", "thinking": "reasoning text"}})

    monkeypatch.setattr(ollama_backend.httpx, "post", fake_post)
    assert _backend()._complete(b"img", "image/png", "p") == "reasoning text"


def test_empty_content_and_thinking_raises(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _Resp({"message": {"content": "", "thinking": ""}})

    monkeypatch.setattr(ollama_backend.httpx, "post", fake_post)
    with pytest.raises(VisionError) as ei:
        _backend()._complete(b"img", "image/png", "p")
    assert ei.value.code == VisionErrorCode.RESPONSE_INVALID


def test_think_unsupported_retries_without_think(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(json)
        if "think" in json:  # first attempt — pretend the model rejects it
            return _Resp({}, status=400, text="model does not support thinking")
        return _Resp({"message": {"content": '{"summary":"s","issues":[]}'}})

    monkeypatch.setattr(ollama_backend.httpx, "post", fake_post)
    out = _backend()._complete(b"img", "image/png", "p")

    assert len(calls) == 2
    assert "think" not in calls[1]                 # retried without the field
    assert out == '{"summary":"s","issues":[]}'


def test_model_not_found_maps_to_ollama_unavailable(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _Resp({}, status=404, text="model not found")

    monkeypatch.setattr(ollama_backend.httpx, "post", fake_post)
    with pytest.raises(VisionError) as ei:
        _backend()._complete(b"img", "image/png", "p")
    assert ei.value.code == VisionErrorCode.OLLAMA_UNAVAILABLE
