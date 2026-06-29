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
import getpass
import json
import sys
from pathlib import Path

from .core import config as cfg
from .core import credentials
from .core.environment import EnvironmentChecker
from .core.models import ProviderConfig
from .core.platform import is_macos, is_windows, module_available


def _resolve_key_arg(value: str | None) -> str | None:
    """If --key is '-', read it hidden via getpass so it never hits argv/logs."""
    if value == "-":
        return getpass.getpass("API key (hidden): ").strip() or None
    return value


def _run_app(args) -> int:
    if not args.no_tray and is_macos() and module_available("rumps"):
        from .tray.macos import run_tray  # noqa: PLC0415

        run_tray()
        return 0
    if not args.no_tray and is_windows() and module_available("pystray"):
        from .tray.windows import run_tray  # noqa: PLC0415

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
        print(f"provider id already exists: {pid}", file=sys.stderr)
        return 1

    key_ref = None
    key_value = _resolve_key_arg(args.key)
    if key_value:
        # Store the key in the OS keychain (plan §7.6); never in config.
        key_ref = f"provider:{pid}"
        credentials.set_key(key_ref, key_value)
    elif args.type != "ollama" and not credentials.has_env_fallback(args.type):
        print(
            f"Warning: no key for '{args.type}'. Register with --key or set an env var.",
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


def _cmd_provider_update(args) -> int:
    config = cfg.load_config()
    provider = config.get_provider(args.id)
    if provider is None:
        print(f"provider not found: {args.id}", file=sys.stderr)
        return 1
    if args.type is not None:
        provider.type = args.type
    if args.model is not None:
        provider.model = args.model
    if args.label is not None:
        provider.label = args.label
    if args.base_url is not None:
        provider.base_url = args.base_url
    key_value = _resolve_key_arg(args.key)
    if key_value is not None:
        # Reuse the existing key_ref if present, else create one.
        provider.key_ref = provider.key_ref or f"provider:{provider.id}"
        credentials.set_key(provider.key_ref, key_value)
    if args.set_default:
        config.default_provider_id = provider.id
    cfg.save_config(config)
    print(json.dumps({"status": "ok", "updated": provider.id, "type": provider.type,
                      "model": provider.model, "base_url": provider.base_url},
                     ensure_ascii=False))
    return 0


def _cmd_provider_remove(args) -> int:
    config = cfg.load_config()
    provider = config.get_provider(args.id)
    if provider is None:
        print(f"provider not found: {args.id}", file=sys.stderr)
        return 1
    if provider.key_ref:
        credentials.delete_key(provider.key_ref)
    config.remove_provider(args.id)
    cfg.save_config(config)
    print(json.dumps({"status": "ok", "removed": args.id,
                      "default": config.default_provider_id}, ensure_ascii=False))
    return 0


def _cmd_provider_consent(args) -> int:
    config = cfg.load_config()
    if not config.set_consent(args.id, not args.revoke):
        print(f"provider not found: {args.id}", file=sys.stderr)
        return 1
    cfg.save_config(config)
    print(json.dumps({"status": "ok", "id": args.id,
                      "consented": not args.revoke}, ensure_ascii=False))
    return 0


def _cmd_provider_list(_args) -> int:
    config = cfg.load_config()
    out = {
        "default_provider_id": config.default_provider_id,
        "last_used_provider_id": config.last_used_provider_id,
        "providers": [
            {"id": p.id, "type": p.type, "model": p.model, "base_url": p.base_url,
             "has_key": p.is_local or bool(credentials.get_key(p.key_ref, provider_type=p.type)),
             "consented": p.is_local or p.consented}
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


def _cmd_autostart(args) -> int:
    from .core import autostart  # noqa: PLC0415

    if args.action == "enable":
        location = autostart.enable()
        print(json.dumps({"status": "ok", "autostart": True, "location": location},
                         ensure_ascii=False))
    elif args.action == "disable":
        autostart.disable()
        print(json.dumps({"status": "ok", "autostart": False}, ensure_ascii=False))
    else:  # status
        print(json.dumps({"autostart": autostart.is_enabled(),
                          "location": autostart.location()}, ensure_ascii=False))
    return 0


def _cmd_capture_analyze(args) -> int:
    from .server.app import capture_and_analyze  # noqa: PLC0415

    result = capture_and_analyze(
        target=args.target,
        monitor_index=args.monitor,
        window_id=args.window_id,
        app_name=args.app_name,
        title_contains=args.title_contains,
        x=args.x, y=args.y, w=args.w, h=args.h,
        prompt=args.prompt,
        backend=args.backend,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vgmcp", description="Vision-Graft MCP")
    parser.add_argument("--no-tray", action="store_true",
                        help="run only the HTTP host in the foreground (no tray)")
    parser.set_defaults(func=_run_app)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="print the environment check result").set_defaults(func=_cmd_check)

    p_prov = sub.add_parser("provider", help="manage vision providers")
    prov_sub = p_prov.add_subparsers(dest="prov_command", required=True)
    p_add = prov_sub.add_parser("add", help="register a provider")
    p_add.add_argument("--type", required=True,
                       choices=["anthropic", "openai", "openrouter", "custom", "ollama"])
    p_add.add_argument("--id", help="provider id (default = type)")
    p_add.add_argument("--label")
    p_add.add_argument("--model", help="model name (defaults to the backend default)")
    p_add.add_argument("--base-url", dest="base_url", help="endpoint for a custom provider")
    p_add.add_argument("--key", help="API key ('-' = hidden prompt; omit to use an env var; stored in the keychain)")
    p_add.add_argument("--set-default", action="store_true")
    p_add.set_defaults(func=_cmd_provider_add)

    p_upd = prov_sub.add_parser("update", help="update a provider")
    p_upd.add_argument("id")
    p_upd.add_argument("--type",
                       choices=["anthropic", "openai", "openrouter", "custom", "ollama"])
    p_upd.add_argument("--model")
    p_upd.add_argument("--label")
    p_upd.add_argument("--base-url", dest="base_url")
    p_upd.add_argument("--key", help="replace the API key ('-' = hidden prompt; stored in the keychain)")
    p_upd.add_argument("--set-default", action="store_true")
    p_upd.set_defaults(func=_cmd_provider_update)

    p_rm = prov_sub.add_parser("remove", help="remove a provider (also deletes its keychain key)")
    p_rm.add_argument("id")
    p_rm.set_defaults(func=_cmd_provider_remove)

    p_cs = prov_sub.add_parser("consent", help="grant/revoke external-transmission consent (§7.9)")
    p_cs.add_argument("id")
    p_cs.add_argument("--revoke", action="store_true", help="revoke consent")
    p_cs.set_defaults(func=_cmd_provider_consent)

    prov_sub.add_parser("list", help="list registered providers").set_defaults(func=_cmd_provider_list)

    p_an = sub.add_parser("analyze", help="analyze an image file")
    p_an.add_argument("image")
    p_an.add_argument("--prompt", default=(
        "Find overlapping/broken parts, misalignment, and clipped/occluded elements "
        "in this UI, and explain them with the likely CSS/style areas to fix."))
    p_an.add_argument("--backend", help="provider id (defaults to the default provider)")
    p_an.set_defaults(func=_cmd_analyze)

    p_as = sub.add_parser("autostart", help="start at login (LaunchAgent / Run key)")
    p_as.add_argument("action", choices=["enable", "disable", "status"], nargs="?",
                      default="status")
    p_as.set_defaults(func=_cmd_autostart)

    p_ca = sub.add_parser("capture-analyze", help="capture then analyze")
    p_ca.add_argument("--target", default="monitor",
                      choices=["monitor", "window", "region", "region_interactive"])
    p_ca.add_argument("--monitor", type=int, default=0)
    p_ca.add_argument("--window-id", dest="window_id", type=int)
    p_ca.add_argument("--app-name", dest="app_name", help="target=window selector (app name)")
    p_ca.add_argument("--title-contains", dest="title_contains", help="target=window selector (title contains)")
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
