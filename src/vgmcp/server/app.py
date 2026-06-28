"""FastMCP app + tool definitions (plan §5).

Tools are thin: they run the lazy environment check (plan §3.2.1.2), then call
shared core logic. On an incomplete environment they return the structured
guide (plan §3.3.2) instead of raising.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from ..core import config as cfg
from ..core.environment import EnvironmentChecker

mcp: FastMCP = FastMCP(
    name="vgmcp",
    instructions=(
        "Vision-Graft MCP gives you an 'eye'. When you modify frontend code or "
        "the user reports a UI issue, capture the screen with take_screenshot, "
        "then analyze it with analyze_vision and trust the returned report as if "
        "you saw it yourself. Never finish a UI fix on a guess. If a tool returns "
        "status=environment_incomplete, relay the guide to the user, wait, then retry."
    ),
)


def _not_implemented(feature: str, milestone: str) -> dict[str, Any]:
    return {
        "status": "not_implemented",
        "feature": feature,
        "message": f"'{feature}'는 마일스톤 {milestone}에서 제공됩니다.",
    }


# --------------------------------------------------------------------------- #
# Environment (plan §5.5, §3.3.3)
# --------------------------------------------------------------------------- #
@mcp.tool
def check_environment() -> dict[str, Any]:
    """현재 실행 환경(런타임/패키지/권한/자격증명/설정)을 점검하고 누락 항목 가이드를 반환한다."""
    status = EnvironmentChecker().check_full()
    if status.ok:
        return {"status": "ok", "message": "환경 구성이 완료되었습니다."}
    return status.to_guide()


# --------------------------------------------------------------------------- #
# Capture (plan §5.1, §5.2) — implemented in M2/M3
# --------------------------------------------------------------------------- #
@mcp.tool
def list_monitors() -> dict[str, Any]:
    """캡처 대상 모니터 목록을 반환한다."""
    env = EnvironmentChecker().check_for_capture()
    if not env.ok:
        return env.to_guide()
    from ..capture import get_capture_backend  # noqa: PLC0415

    backend = get_capture_backend()
    if backend is None:
        return _not_implemented("list_monitors", "M2")
    return {"status": "ok", "monitors": [m.model_dump() for m in backend.list_monitors()]}


@mcp.tool
def list_windows() -> dict[str, Any]:
    """캡처 대상이 될 수 있는 열린 윈도우 목록(앱명/제목/ID)을 반환한다."""
    env = EnvironmentChecker().check_for_capture()
    if not env.ok:
        return env.to_guide()
    from ..capture import get_capture_backend  # noqa: PLC0415

    backend = get_capture_backend()
    if backend is None:
        return _not_implemented("list_windows", "M3")
    return {"status": "ok", "windows": [w.model_dump() for w in backend.list_windows()]}


@mcp.tool
def take_screenshot(
    target: str = "monitor",
    monitor_index: int = 0,
    window_id: int | None = None,
    app_name: str | None = None,
    title_contains: str | None = None,
    x: int | None = None,
    y: int | None = None,
    w: int | None = None,
    h: int | None = None,
) -> dict[str, Any]:
    """화면을 캡처해 타겟 폴더에 저장한다.

    target:
      - 'monitor'            : 모니터 전체화면 (monitor_index)
      - 'window'             : 특정 윈도우 (window_id, 또는 app_name/title_contains 셀렉터)
      - 'region'             : 좌표 영역 (x, y, w, h; 주 디스플레이 좌상단 기준 픽셀)
      - 'region_interactive' : 사용자가 마우스로 사각형 영역을 드래그 선택 (사용자 조작 필요)

    작은 영역은 분석 시 원본 그대로, 큰 영역은 자동 다운스케일되어 전송된다(§7.5).
    """
    from ..core.capture_service import perform_capture  # noqa: PLC0415

    return perform_capture(
        target,
        monitor_index=monitor_index,
        window_id=window_id,
        app_name=app_name,
        title_contains=title_contains,
        x=x, y=y, w=w, h=h,
    )


# --------------------------------------------------------------------------- #
# Vision (plan §5.3, §5.4) — implemented in M1
# --------------------------------------------------------------------------- #
@mcp.tool
def analyze_vision(
    image_path: str,
    prompt: str = (
        "현재 UI에서 겹치거나 깨진 부분, 정렬 불량, 요소 가려짐/잘림을 찾아 "
        "원인이 될 만한 CSS/스타일 영역과 함께 설명해 줘."
    ),
    backend: str | None = None,
) -> dict[str, Any]:
    """이미지 경로 + 프롬프트를 받아 비전 백엔드로 분석하고 정형 리포트를 반환한다."""
    env = EnvironmentChecker().check_for_vision(backend)
    if not env.ok:
        return env.to_guide()
    from .vision_service import run_analysis  # noqa: PLC0415

    return run_analysis(Path(image_path).expanduser(), prompt, backend)


@mcp.tool
def capture_and_analyze(
    target: str = "monitor",
    monitor_index: int = 0,
    window_id: int | None = None,
    app_name: str | None = None,
    title_contains: str | None = None,
    x: int | None = None,
    y: int | None = None,
    w: int | None = None,
    h: int | None = None,
    prompt: str | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    """캡처→분석을 한 번에 수행하는 편의 체인(plan §5.4). target은 take_screenshot과 동일."""
    shot = take_screenshot(
        target=target, monitor_index=monitor_index, window_id=window_id,
        app_name=app_name, title_contains=title_contains, x=x, y=y, w=w, h=h
    )
    if shot.get("status") != "ok":
        return shot
    kwargs: dict[str, Any] = {"image_path": shot["path"], "backend": backend}
    if prompt is not None:
        kwargs["prompt"] = prompt
    return analyze_vision(**kwargs)


# --------------------------------------------------------------------------- #
# Settings (plan §5.6)
# --------------------------------------------------------------------------- #
@mcp.tool
def get_config() -> dict[str, Any]:
    """현재 설정(타겟 폴더, 등록된 provider, 기본 provider 등)을 반환한다. API 키는 포함하지 않는다."""
    config = cfg.load_config()
    return {
        "status": "ok",
        "target_folder": config.target_folder,
        "default_provider_id": config.default_provider_id,
        "last_used_provider_id": config.last_used_provider_id,
        "providers": [
            {"id": p.id, "type": p.type, "label": p.label, "model": p.model, "is_local": p.is_local}
            for p in config.providers
        ],
    }


@mcp.tool
def set_target_folder(path: str) -> dict[str, Any]:
    """캡처 이미지가 저장될 타겟 폴더를 설정한다(트레이앱과 동일 설정 파일 공유)."""
    folder = Path(path).expanduser()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"status": "error", "message": f"폴더를 생성할 수 없습니다: {exc}"}
    config = cfg.load_config()
    config.target_folder = str(folder)
    cfg.save_config(config)
    return {"status": "ok", "target_folder": str(folder)}


def get_app() -> FastMCP:
    return mcp
