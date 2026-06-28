"""`vgmcp` entry point — resident tray app + embedded HTTP host (plan §2.4).

Subcommands:
  (none)           resident tray app (macOS) or foreground host
  check            print environment check and exit
  provider add     register a vision provider (for testing before the M4 UI)
  provider list    list registered providers
  analyze <image>  analyze an image with the default/named backend
  capture-analyze  capture (monitor/region) then analyze in one shot
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import config as cfg
from .core import credentials
from .core.environment import EnvironmentChecker
from .core.models import ProviderConfig
from .core.platform import is_macos, module_available


def _run_app(args) -> int:
    if not args.no_tray and is_macos() and module_available("rumps"):
        from .tray.macos import run_tray  # noqa: PLC0415

        run_tray()
        return 0
    from .server import host  # noqa: PLC0415

    print(f"VGMCP host: {host.server_url()}", file=sys.stderr)
    host.run_http()
    return 0


def _cmd_check(_args) -> int:
    status = EnvironmentChecker().check_full()
    print(json.dumps(status.model_dump(), ensure_ascii=False, indent=2))
    return 0 if status.ok else 1


def _cmd_provider_add(args) -> int:
    config = cfg.load_config()
    pid = args.id or args.type
    if config.get_provider(pid):
        print(f"이미 존재하는 provider id: {pid}", file=sys.stderr)
        return 1

    key_ref = None
    if args.key:
        # Store the key in the OS keychain (plan §7.6); never in config.
        key_ref = f"provider:{pid}"
        credentials.set_key(key_ref, args.key)
    elif args.type != "ollama" and not credentials.has_env_fallback(args.type):
        print(
            f"경고: '{args.type}' 키가 없습니다. --key로 등록하거나 환경변수를 설정하세요.",
            file=sys.stderr,
        )

    provider = ProviderConfig(
        id=pid,
        type=args.type,
        label=args.label or pid,
        model=args.model or "",
        base_url=args.base_url,
        key_ref=key_ref,
    )
    config.add_provider(provider)
    if args.set_default:
        config.default_provider_id = pid
    cfg.save_config(config)
    print(json.dumps({"status": "ok", "added": pid, "default": config.default_provider_id},
                     ensure_ascii=False))
    return 0


def _cmd_provider_list(_args) -> int:
    config = cfg.load_config()
    out = {
        "default_provider_id": config.default_provider_id,
        "last_used_provider_id": config.last_used_provider_id,
        "providers": [
            {"id": p.id, "type": p.type, "model": p.model, "base_url": p.base_url,
             "has_key": p.is_local or bool(credentials.get_key(p.key_ref, provider_type=p.type))}
            for p in config.providers
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_analyze(args) -> int:
    from .server.vision_service import run_analysis  # noqa: PLC0415

    env = EnvironmentChecker().check_for_vision(args.backend)
    if not env.ok:
        print(json.dumps(env.to_guide(), ensure_ascii=False, indent=2))
        return 1
    result = run_analysis(Path(args.image).expanduser(), args.prompt, args.backend)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


def _cmd_capture_analyze(args) -> int:
    from .server.app import capture_and_analyze  # noqa: PLC0415

    result = capture_and_analyze(
        target=args.target,
        monitor_index=args.monitor,
        x=args.x, y=args.y, w=args.w, h=args.h,
        prompt=args.prompt,
        backend=args.backend,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vgmcp", description="Vision-Graft MCP")
    parser.add_argument("--no-tray", action="store_true",
                        help="트레이 없이 HTTP 호스트만 포그라운드로 실행")
    parser.set_defaults(func=_run_app)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="환경 점검 결과 출력").set_defaults(func=_cmd_check)

    p_prov = sub.add_parser("provider", help="비전 provider 관리")
    prov_sub = p_prov.add_subparsers(dest="prov_command", required=True)
    p_add = prov_sub.add_parser("add", help="provider 등록")
    p_add.add_argument("--type", required=True,
                       choices=["anthropic", "openai", "openrouter", "custom", "ollama"])
    p_add.add_argument("--id", help="provider id (기본=type)")
    p_add.add_argument("--label")
    p_add.add_argument("--model", help="모델명 (미지정 시 백엔드 기본값)")
    p_add.add_argument("--base-url", dest="base_url", help="custom provider의 엔드포인트")
    p_add.add_argument("--key", help="API 키 (미지정 시 환경변수 사용; 키체인에 저장)")
    p_add.add_argument("--set-default", action="store_true")
    p_add.set_defaults(func=_cmd_provider_add)
    prov_sub.add_parser("list", help="등록된 provider 목록").set_defaults(func=_cmd_provider_list)

    p_an = sub.add_parser("analyze", help="이미지 파일 비전 분석")
    p_an.add_argument("image")
    p_an.add_argument("--prompt", default=(
        "현재 UI에서 겹치거나 깨진 부분, 정렬 불량, 요소 가려짐/잘림을 찾아 "
        "원인이 될 만한 CSS/스타일 영역과 함께 설명해 줘."))
    p_an.add_argument("--backend", help="provider id (미지정 시 기본값)")
    p_an.set_defaults(func=_cmd_analyze)

    p_ca = sub.add_parser("capture-analyze", help="캡처 후 분석")
    p_ca.add_argument("--target", default="monitor",
                      choices=["monitor", "window", "region", "region_interactive"])
    p_ca.add_argument("--monitor", type=int, default=0)
    p_ca.add_argument("--x", type=int)
    p_ca.add_argument("--y", type=int)
    p_ca.add_argument("--w", type=int)
    p_ca.add_argument("--h", type=int)
    p_ca.add_argument("--prompt")
    p_ca.add_argument("--backend")
    p_ca.set_defaults(func=_cmd_capture_analyze)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
