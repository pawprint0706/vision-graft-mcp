"""EnvironmentChecker (plan §3.2, §3.3).

Verifies runtime / packages / permissions / credentials / settings and turns
any gap into a structured guide instead of a silent failure.

Two check scopes (plan §3.2.1):
  * full check         — tray startup, status icon
  * lazy/targeted check — right before a specific MCP tool runs
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import credentials
from .config import AppConfig, load_config
from .models import EnvCategory, EnvIssue, EnvStatus
from .platform import is_macos, is_windows, module_available

MIN_PYTHON = (3, 11)

# Package -> (pip name, why) for the active platform's capture/tray stack.
_MACOS_CAPTURE_PKGS = {
    "ScreenCaptureKit": ("pyobjc-framework-ScreenCaptureKit", "macOS 화면/윈도우 캡처(ScreenCaptureKit)"),
    "Quartz": ("pyobjc-framework-Quartz", "macOS 윈도우 열거 보조"),
    "AppKit": ("pyobjc-framework-Cocoa", "macOS 앱↔PID 매핑/트레이"),
}
_WINDOWS_CAPTURE_PKGS = {
    "win32gui": ("pywin32", "Windows 윈도우 열거"),
    "mss": ("mss", "Windows 영역 캡처"),
}


def _check_python() -> list[EnvIssue]:
    if sys.version_info < MIN_PYTHON:
        return [
            EnvIssue(
                category=EnvCategory.RUNTIME,
                name=f"python>={MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
                reason=f"현재 {sys.version_info.major}.{sys.version_info.minor}, "
                f"최소 {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 필요",
            )
        ]
    return []


def _check_capture_packages() -> list[EnvIssue]:
    pkgs = _MACOS_CAPTURE_PKGS if is_macos() else _WINDOWS_CAPTURE_PKGS if is_windows() else {}
    issues: list[EnvIssue] = []
    for module, (pip_name, reason) in pkgs.items():
        if not module_available(module):
            issues.append(
                EnvIssue(
                    category=EnvCategory.PACKAGE,
                    name=pip_name,
                    reason=reason,
                    install_command=f"pip install {pip_name}",
                    platform="macos" if is_macos() else "windows",
                )
            )
    return issues


def _check_capture_permission() -> list[EnvIssue]:
    """macOS Screen Recording permission via a dummy capture (plan §3.2.2)."""
    if not is_macos():
        return []
    try:
        from ..capture import get_capture_backend  # noqa: PLC0415

        backend = get_capture_backend()
        if backend is not None and backend.check_permission():
            return []
    except Exception:  # noqa: BLE001 — backend missing/raised => treat as not granted
        pass
    return [
        EnvIssue(
            category=EnvCategory.PERMISSION,
            name="screen_recording",
            platform="macos",
            reason="권한 없으면 캡처가 검은/투명 이미지로 실패",
            guide="시스템 설정 > 개인정보 보호 및 보안 > 화면 기록에서 본 앱을 허용 후 재시도",
        )
    ]


def _check_default_credential(config: AppConfig) -> list[EnvIssue]:
    """Verify the effective default provider has usable credentials (plan §3.2.2)."""
    provider = config.effective_default()
    if provider is None:
        return [
            EnvIssue(
                category=EnvCategory.CREDENTIAL,
                name="vision_provider",
                reason="등록된 비전 백엔드가 없습니다",
                guide="트레이 '설정 > 비전 백엔드 관리'에서 provider를 추가하십시오.",
            )
        ]
    if provider.is_local:
        return []  # Ollama needs no key (plan §7.9)
    key = credentials.get_key(provider.key_ref, provider_type=provider.type)
    if not key:
        return [
            EnvIssue(
                category=EnvCategory.CREDENTIAL,
                name=f"api_key:{provider.id}",
                reason=f"'{provider.label or provider.id}' provider의 API 키를 찾을 수 없습니다",
                guide="트레이 '설정 > 비전 백엔드 관리'에서 API 키를 등록하거나 환경변수를 설정하십시오.",
            )
        ]
    return []


def _check_target_folder(config: AppConfig) -> list[EnvIssue]:
    folder = Path(config.target_folder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return [
            EnvIssue(
                category=EnvCategory.SETTING,
                name="target_folder",
                reason=f"타겟 폴더를 생성/쓰기할 수 없습니다: {exc}",
                guide="트레이 '설정 > 타겟 폴더 설정'에서 쓰기 가능한 폴더를 지정하십시오.",
            )
        ]
    import os  # noqa: PLC0415

    if not os.access(folder, os.W_OK):
        return [
            EnvIssue(
                category=EnvCategory.SETTING,
                name="target_folder",
                reason=f"타겟 폴더에 쓰기 권한이 없습니다: {folder}",
                guide="트레이 '설정 > 타겟 폴더 설정'에서 쓰기 가능한 폴더를 지정하십시오.",
            )
        ]
    return []


class EnvironmentChecker:
    """Runs environment checks and produces an EnvStatus (plan §3)."""

    def __init__(self, config: AppConfig | None = None) -> None:
        # An explicit config is pinned; otherwise reload fresh on every access so
        # live edits (e.g. re-adding a provider from the tray) are picked up.
        self._config = config

    @property
    def config(self) -> AppConfig:
        return self._config if self._config is not None else load_config()

    def check_full(self) -> EnvStatus:
        """Full sweep — tray startup (plan §3.2.1.1)."""
        issues: list[EnvIssue] = []
        issues += _check_python()
        issues += _check_capture_packages()
        issues += _check_capture_permission()
        issues += _check_default_credential(self.config)
        issues += _check_target_folder(self.config)
        return _status(issues)

    def check_for_capture(self) -> EnvStatus:
        """Lazy check before take_screenshot (plan §3.2.1.2)."""
        issues: list[EnvIssue] = []
        issues += _check_python()
        issues += _check_capture_packages()
        issues += _check_capture_permission()
        issues += _check_target_folder(self.config)
        return _status(issues)

    def detailed(self) -> list[tuple[str, bool, str]]:
        """Per-item pass/fail report for the full check (plan §3.2.2).

        Returns a list of (label, ok, detail) for display in a dialog.
        """
        from .i18n import tr  # noqa: PLC0415

        config = self.config
        report: list[tuple[str, bool, str]] = []

        def add(label: str, issues: list[EnvIssue]) -> None:
            ok = not issues
            detail = tr("정상", "OK") if ok else "; ".join(i.reason for i in issues)
            report.append((label, ok, detail))

        add("Python ≥ 3.11", _check_python())
        add(tr("캡처 패키지", "Capture packages"), _check_capture_packages())
        add(tr("화면 기록 권한", "Screen Recording permission"), _check_capture_permission())
        add(tr("비전 백엔드 자격증명", "Vision backend credential"),
            _check_default_credential(config))
        add(tr("타겟 폴더 쓰기 가능", "Target folder writable"), _check_target_folder(config))
        return report

    def check_for_vision(self, provider_id: str | None = None) -> EnvStatus:
        """Lazy check before analyze_vision (plan §3.2.1.2)."""
        issues: list[EnvIssue] = []
        issues += _check_python()
        if provider_id:
            provider = self.config.get_provider(provider_id)
            if provider is None:
                issues.append(
                    EnvIssue(
                        category=EnvCategory.SETTING,
                        name=f"provider:{provider_id}",
                        reason=f"지정한 provider를 찾을 수 없습니다: {provider_id}",
                        guide="check_environment로 등록된 provider 목록을 확인하십시오.",
                    )
                )
            elif not provider.is_local and not credentials.get_key(
                provider.key_ref, provider_type=provider.type
            ):
                issues.append(
                    EnvIssue(
                        category=EnvCategory.CREDENTIAL,
                        name=f"api_key:{provider_id}",
                        reason=f"'{provider_id}' provider의 API 키가 없습니다",
                        guide="트레이 '설정 > 비전 백엔드 관리'에서 키를 등록하십시오.",
                    )
                )
        else:
            issues += _check_default_credential(self.config)
        return _status(issues)


def _status(issues: list[EnvIssue]) -> EnvStatus:
    blocking = len(issues) > 0
    return EnvStatus(ok=not blocking, blocking=blocking, missing=issues)
