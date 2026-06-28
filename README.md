# Vision-Graft MCP (VGMCP)

Gives vision-blind LLMs an **eye**: OS-level screenshot capture + external
vision-model analysis, exposed over the **MCP** standard. A text-only coding
model can capture the running UI, get a structured visual report, and debug
layout/alignment/clipping bugs it otherwise can't see.

See [`docs/plan.md`](docs/plan.md) for the full specification and
[`docs/idea.md`](docs/idea.md) for the original concept.

## Architecture (plan §2.4)

The **tray app** hosts a resident loopback HTTP/SSE MCP server holding the
shared core (capture / vision / clipboard / environment check). MCP clients
(Cursor/Windsurf) register a thin **stdio adapter** that proxies to it, so both
the user (tray) and the LLM (MCP) drive the same core, target folder, and config.

```
Client (LLM) ──stdio──> vgmcp-adapter ──HTTP──> Tray app (resident host + shared core)
User ────────────────────────────────────────> Tray menu ─┘
```

## Status

Under active development. Milestones (plan §11):

- **M0** ✅ scaffold, shared core interfaces, EnvironmentChecker, host + stdio adapter
- **M1** ✅ vision backends (Anthropic / OpenAI-compatible / Ollama) + preprocessing + parse fallback
- **M2/M3** ✅ ScreenCaptureKit monitor + window capture (macOS) + region capture (drag/coords)
- **M4** ✅ tray menu + status icon + clipboard supporter + backend management UI
- **M5** environment loop + onboarding + consent
- **M6** Windows port · **M7** Ollama, convenience chain, stabilization

## Install (dev)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[macos,anthropic,openai]"   # macOS dev with cloud backends
```

## Run

```bash
vgmcp            # resident tray app + embedded host (macOS)
vgmcp check      # print environment check result and exit
vgmcp --no-tray  # run the HTTP host in the foreground (headless)

vgmcp autostart enable    # start the tray at login (LaunchAgent); also a tray toggle
vgmcp autostart disable
vgmcp autostart status
```

Register the adapter in your MCP client (e.g. Cursor):

```json
{ "mcpServers": { "vgmcp": { "command": "vgmcp-adapter" } } }
```

Requires Python ≥ 3.11. macOS target is **14 (Sonoma)+** (ScreenCaptureKit).

## Vision providers (CLI)

Until the tray management UI (M4) lands, providers are managed from the CLI.
API keys go to the OS keychain (never to config); env vars
(`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY`) are honored as a
fallback. The default provider is the first registered, then the last used
(plan §7.3).

```bash
# Register a provider (key via env var — nothing stored)
export ANTHROPIC_API_KEY="sk-ant-..."
vgmcp provider add --type anthropic --set-default

# Register with the key stored in the keychain
vgmcp provider add --type openrouter --model "openai/gpt-4o" --key "sk-or-..." --set-default

# Custom OpenAI-compatible endpoint
vgmcp provider add --type custom --base-url "https://gateway.example/v1" \
    --model "..." --key "..."

vgmcp provider list                       # show providers (+ whether a key resolves)
vgmcp provider update <id> --model "..."  # change type/model/base-url/key/default
vgmcp provider remove <id>                # delete provider + its keychain key
```

`--type` is one of `anthropic | openai | openrouter | custom | ollama`
(Ollama is local — no key, no external transmission). `openrouter`/`custom`
require a `--model`; `custom` also requires `--base-url`.

## Test the real vision loop

```bash
vgmcp capture-analyze --target monitor               # capture screen + analyze
vgmcp capture-analyze --target region_interactive    # drag-select a region, then analyze
vgmcp capture-analyze --target region --x 100 --y 100 --w 600 --h 400
vgmcp analyze /path/to/screenshot.png                # analyze an existing image
```

Small regions are sent as-is; large captures are downscaled to a ~1568px long
edge before transmission (plan §7.5).
