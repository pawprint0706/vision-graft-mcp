"""Shared data models (plan §5, §6, §7).

Pydantic models so they serialize cleanly into MCP tool outputs and the
config file.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Capture (plan §6)
# --------------------------------------------------------------------------- #
class MonitorInfo(BaseModel):
    index: int
    width: int
    height: int
    dpi_scale: float = 1.0
    primary: bool = False


class WindowBounds(BaseModel):
    x: int
    y: int
    w: int
    h: int


class WindowInfo(BaseModel):
    window_id: int  # macOS CGWindowID / Windows HWND
    app_name: str
    title: str = ""
    pid: int | None = None
    bounds: WindowBounds | None = None
    on_screen: bool = True


class CaptureResult(BaseModel):
    status: Literal["ok"] = "ok"
    path: str
    width: int
    height: int
    source: str = ""  # e.g. "monitor0" / "Safari"


# --------------------------------------------------------------------------- #
# Vision (plan §5.3, §7)
# --------------------------------------------------------------------------- #
Severity = Literal["high", "medium", "low"]


class VisionIssue(BaseModel):
    severity: Severity = "medium"
    region: str = ""
    element: str = ""
    description: str = ""
    css_hint: str = ""


class VisionReportBody(BaseModel):
    summary: str = ""
    issues: list[VisionIssue] = Field(default_factory=list)
    raw_text: str = ""
    # True when structured parsing failed and we fell back to raw_text (plan §7.7).
    parse_degraded: bool = False


class VisionResult(BaseModel):
    status: Literal["ok"] = "ok"
    backend: str
    report: VisionReportBody


# --------------------------------------------------------------------------- #
# Provider registry (plan §7.2, §7.3)
# --------------------------------------------------------------------------- #
ProviderType = Literal["anthropic", "openai", "openrouter", "custom", "ollama"]


class ProviderConfig(BaseModel):
    """One registered vision provider (plan §7.3).

    API keys are NOT stored here — only `key_ref`, an identifier into the OS
    credential store (plan §7.6).
    """

    id: str
    type: ProviderType
    label: str = ""
    model: str = ""
    base_url: Optional[str] = None  # required for type=="custom"; defaulted for others
    key_ref: Optional[str] = None   # keyring identifier; None for ollama
    # Whether the user already consented to external transmission (plan §7.9).
    consented: bool = False

    @property
    def is_local(self) -> bool:
        return self.type == "ollama"


# --------------------------------------------------------------------------- #
# Environment check (plan §3)
# --------------------------------------------------------------------------- #
class EnvCategory(str, Enum):
    RUNTIME = "runtime"
    PACKAGE = "package"
    PERMISSION = "permission"
    CREDENTIAL = "credential"
    SETTING = "setting"


class EnvIssue(BaseModel):
    category: EnvCategory
    name: str
    reason: str
    install_command: str | None = None
    guide: str | None = None
    platform: str | None = None


class EnvStatus(BaseModel):
    """Result of an environment check (plan §3.2, §3.3)."""

    ok: bool
    blocking: bool
    missing: list[EnvIssue] = Field(default_factory=list)

    def to_guide(self) -> dict:
        """Structured guide returned from MCP tools when incomplete (plan §3.3.2)."""
        return {
            "status": "environment_incomplete",
            "blocking": self.blocking,
            "missing": [m.model_dump(exclude_none=True) for m in self.missing],
            "message_for_user": "환경 구성이 필요합니다. 아래 항목을 해결한 뒤 다시 시도해 주세요.",
            "next_action": "사용자에게 위 가이드를 전달하고, 해결 완료 후 동일 도구를 재호출하십시오.",
        }
