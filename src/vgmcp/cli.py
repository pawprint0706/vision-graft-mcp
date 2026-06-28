"""`vgmcp` entry point — resident tray app + embedded HTTP host (plan §2.4)."""

from __future__ import annotations

import argparse
import json
import sys

from .core.environment import EnvironmentChecker
from .core.platform import is_macos, module_available


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vgmcp", description="Vision-Graft MCP")
    parser.add_argument(
        "--no-tray", action="store_true", help="트레이 없이 HTTP 호스트만 포그라운드로 실행"
    )
    parser.add_argument("--check", action="store_true", help="환경 점검 결과만 출력하고 종료")
    args = parser.parse_args(argv)

    if args.check:
        status = EnvironmentChecker().check_full()
        print(json.dumps(status.model_dump(), ensure_ascii=False, indent=2))
        return 0 if status.ok else 1

    if not args.no_tray and is_macos() and module_available("rumps"):
        from .tray.macos import run_tray  # noqa: PLC0415

        run_tray()
        return 0

    # Headless / no tray stack: run the host in the foreground.
    from .server import host  # noqa: PLC0415

    print(f"VGMCP host: {host.server_url()}", file=sys.stderr)
    host.run_http()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
