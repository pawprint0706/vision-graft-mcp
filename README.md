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
- **M1** vision backends (Anthropic / OpenAI-compatible / Ollama) + preprocessing + parse fallback
- **M2/M3** ScreenCaptureKit monitor + window capture (macOS)
- **M4** tray menu + status + clipboard supporter + backend management UI
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
vgmcp --check    # print environment check result and exit
vgmcp --no-tray  # run the HTTP host in the foreground (headless)
```

Register the adapter in your MCP client (e.g. Cursor):

```json
{ "mcpServers": { "vgmcp": { "command": "vgmcp-adapter" } } }
```

Requires Python ≥ 3.11. macOS target is **14 (Sonoma)+** (ScreenCaptureKit).
