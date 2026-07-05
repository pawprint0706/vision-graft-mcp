# Vision-Graft MCP (VGMCP)

[한국어](../README.md) · **English**

A screenshot + vision-analysis MCP server that gives an **eye** to AI coding
models that cannot see images.

Many fast or local LLMs cannot read images. From code alone they cannot tell
whether a button is cut off or two elements overlap. VGMCP captures your
screen, sends it to a **vision-capable model**, and hands the AI back a
**written report** it can read — so the AI can actually fix visual bugs.

- **The AI uses it** — via the [MCP](https://modelcontextprotocol.io) standard
  from Claude Code, Cursor, Claude Desktop, and other MCP clients.
- **You use it** — directly from the menu-bar (macOS) / system-tray (Windows)
  icon: capture and analyze without any AI tool.

---

## How it works

```
AI coding tool (Claude Code · Cursor · Claude Desktop …)
      │  stdio (MCP)
      ▼
vgmcp-adapter ──HTTP──▶ VGMCP tray app = resident MCP host (127.0.0.1:8765/mcp)
(thin proxy)              ├─ screen capture: monitor · window · region
                          ├─ vision backend call → returns a written report
                          │    OpenRouter · Anthropic · OpenAI · custom · Ollama (local)
                          └─ tray menu: you can drive the same features yourself
```

- The user (tray) and the AI (MCP) share the **same core and settings**
  (target folder, vision backends).
- If the tray app is not running, the adapter exposes a single diagnostic tool
  (`vgmcp_status`) that tells the AI to ask you to start it. **The tray app
  must be running for the AI side to work.**
- The host binds to loopback (127.0.0.1) only — it is not reachable from
  outside your machine.

## Requirements

| Item | Requirement |
|---|---|
| OS | macOS 14 (Sonoma)+ or Windows 10/11 |
| Python | 3.11+ ([python.org/downloads](https://www.python.org/downloads/); on Windows tick "Add Python to PATH") |
| Vision backend | One cloud API key **or** local [Ollama](https://ollama.com) (see table) |
| AI tool | Anything that supports MCP over stdio |

| Backend type (`--type`) | Default model | Where to get a key |
|---|---|---|
| `openrouter` (recommended) | `anthropic/claude-sonnet-4.6` | <https://openrouter.ai/keys> |
| `anthropic` | `claude-sonnet-4-6` | <https://console.anthropic.com/> |
| `openai` | `gpt-5.4` | <https://platform.openai.com/api-keys> |
| `custom` | you choose (`--base-url` required) | any OpenAI-compatible endpoint |
| `ollama` | `llava:7b` | no key — runs on your machine |

If you leave the model empty, the default model above is used.

---

## Quick start

> 🤖 **Using an AI agent?** Clone the repo, show your agent this README, and
> say "install this and register the MCP server". The agent will follow the
> [instructions for AI agents](#instructions-for-ai-agents) and do the steps
> below for you.

### 1. Install

One double-click. It creates a `.venv` virtual environment and installs VGMCP.
Safe to re-run (it stops any running instance and reinstalls).

| OS | How |
|---|---|
| Windows | **double-click `install_win.bat`** |
| macOS | **double-click `install_mac.command`** (if blocked: right-click → Open) |

You're done when it prints "✅ 설치 완료 / Install complete".

### 2. Start the app

| OS | How | Icon location |
|---|---|---|
| Windows | **double-click `start_win.bat`** | system tray (by the clock; may be under the `^` overflow) |
| macOS | **double-click `start_mac.command`** | top-right menu bar |

- Click the icon to open the menu. Colors: OK (theme-adaptive white/black or
  green) · 🟡 something optional is missing · 🔴 needs attention (click for
  guidance).
- The start scripts always do a **full restart** (stop a running instance,
  then launch fresh).
- Start at login: menu **Settings → Start at login** (or
  `vgmcp autostart enable`).

### 3. Register a vision backend

Tray icon → **Settings → Manage vision backends → Add…** and enter the type,
name, model, and API key one field at a time (the key field is masked). Grant
**external-transmission consent** and **set as default** in the same submenu.
You can change the model later via **Change model name**.

Prefer the terminal? (command prefix: Windows `.\.venv\Scripts\vgmcp.exe`,
macOS `./.venv/bin/vgmcp`):

```bash
# e.g. OpenRouter — `--key -` asks for the key with a hidden prompt
./.venv/bin/vgmcp provider add --type openrouter --key - --set-default
./.venv/bin/vgmcp provider consent openrouter   # one-time consent to send screenshots

# e.g. Ollama (local · no key, no consent)
ollama pull llava:7b
./.venv/bin/vgmcp provider add --type ollama --set-default
```

> **Local-model tip** — pick a **non-reasoning** vision model that fits your
> VRAM. Reasoning VLMs (e.g. `qwen3-vl`) tend to spend all tokens "thinking"
> and return empty answers. For an 8 GB GPU, `llava:7b` (~4.7 GB) is the
> recommended pick. Use a cloud backend when you need precise analysis.

### 4. Screen-recording permission (macOS only)

In **System Settings → Privacy & Security → Screen Recording**, enable the app
that launches VGMCP (usually Terminal), then quit and restart the app.
**Windows needs no permission.** Verify readiness anytime with `vgmcp check`.

### 5. Register with your AI tool (MCP)

Register the adapter (`vgmcp-adapter`) with its **absolute path**.

- Windows: `<project path>\.venv\Scripts\vgmcp-adapter.exe`
- macOS: `<project path>/.venv/bin/vgmcp-adapter`

**Claude Code:**

```bash
claude mcp add vgmcp -- "C:\path\to\vision-graft-mcp\.venv\Scripts\vgmcp-adapter.exe"  # Windows
claude mcp add vgmcp -- "/path/to/vision-graft-mcp/.venv/bin/vgmcp-adapter"            # macOS
```

**Cursor / Claude Desktop / others (JSON; escape `\` as `\\`):**

```json
{ "mcpServers": { "vgmcp": { "command": "<absolute path to the adapter>" } } }
```

| Tool | Config location |
|---|---|
| Cursor | `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` in a project |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |

Restart the AI tool; VGMCP tools such as `take_screenshot` should appear.
Then try asking your AI:

> "Run the app, take a screenshot, and check whether the layout is broken."

---

## Instructions for AI agents

> This section is written for AI agents to execute as-is. When the user asks
> you to install this repository, follow the steps in order.
> Precondition: the current working directory is the repository root.

**0. Check Python** — `python --version` (Windows) / `python3 --version`
(macOS) must be 3.11+. If missing or older, ask the user to install it from
<https://www.python.org/downloads/> and stop.

**1. Install** — safe to run repeatedly (it force-stops a running VGMCP and
reinstalls, so warn the user first if they may be using it). Success: the
output contains `설치 완료` or `Install complete`.

```powershell
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_win.ps1
```

```bash
# macOS
chmod +x install_mac.command && ./install_mac.command
```

**2. Start the tray app** — it launches detached, so the command returns
immediately.

```powershell
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_win.ps1
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8765/mcp   # any HTTP status code = host is up
```

```bash
# macOS
./start_mac.command
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/mcp
```

**3. Register a vision backend** — pick exactly one path
(command prefix: Windows `.\.venv\Scripts\vgmcp.exe`, macOS `./.venv/bin/vgmcp`).

- **(A) Ollama — fully automatic; no key, no consent.** When Ollama is
  installed or the user wants local processing:

  ```bash
  ollama pull llava:7b
  ./.venv/bin/vgmcp provider add --type ollama --set-default
  ```

- **(B) Cloud — key from an environment variable.** If one of
  `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` is already set
  as a **user/system-level environment variable**, register without `--key`
  (the key is read from the environment at runtime). A shell-session-only
  variable is NOT visible to the tray-app process.

  ```bash
  ./.venv/bin/vgmcp provider add --type openrouter --set-default
  ```

- **(C) Cloud — key entered directly.** The API key is a secret. **Never pass
  it as a command argument** (it would land in shell history). Ask the user to
  run the command below themselves (`--key -` = hidden prompt), or point them
  to the tray menu (Settings → Manage vision backends → Add…).

  ```bash
  ./.venv/bin/vgmcp provider add --type openrouter --key - --set-default
  ```

- **Cloud only — transmission consent.** A one-time consent to send
  screenshots to that cloud provider. **Ask the user for confirmation first**,
  then run (not needed for Ollama):

  ```bash
  ./.venv/bin/vgmcp provider consent openrouter
  ```

**4. Verify**

```bash
./.venv/bin/vgmcp check            # exit 0 = healthy
./.venv/bin/vgmcp provider list    # the backend should show "has_key": true, "consented": true
```

If `check` reports missing items, follow each item's `guide` /
`install_command` or relay it to the user. **You cannot grant the macOS
screen-recording permission yourself** — ask the user to enable it in System
Settings → Privacy & Security → Screen Recording.

**5. Register the MCP server** — use the adapter's **absolute path**.
Windows: `<repo absolute path>\.venv\Scripts\vgmcp-adapter.exe` ·
macOS: `<repo absolute path>/.venv/bin/vgmcp-adapter`

- Claude Code: `claude mcp add vgmcp -- <absolute adapter path>`
  (add `--scope user` to enable it in every project)
- For tools configured via JSON (Cursor, Claude Desktop, …), **merge** the
  entry below into the file's `mcpServers`. Do not delete existing servers or
  overwrite the whole file.

  ```json
  { "mcpServers": { "vgmcp": { "command": "<absolute adapter path>" } } }
  ```

**6. Final check** — restart (reconnect) the MCP client and call the
`check_environment` tool; expect `"status": "ok"`. If only a `vgmcp_status`
tool is listed, the tray app is down → repeat step 2.

**Agent cautions**

- Whenever you need a screenshot, always use the `take_screenshot` tool. Do
  not write your own capture script (PowerShell, `screencapture`,
  `PIL.ImageGrab`, …).
- `region_interactive` capture and tray-menu operations require user
  interaction.

---

## MCP tools

| Tool | What it does |
|---|---|
| `take_screenshot` | Capture the screen, save to the target folder, return the path. `target`: `monitor` · `window` (`app_name`/`title_contains`/`window_id`) · `region` (x·y·w·h) · `region_interactive` (user drag-select). Can be used standalone, without analysis |
| `analyze_vision` | Analyze an image file + prompt with the vision backend; returns a written report |
| `capture_and_analyze` | Capture and analyze in one call |
| `list_monitors` / `list_windows` | List capturable monitors / windows |
| `check_environment` | Check runtime · packages · permissions · keys · settings; returns a fix guide per gap |
| `get_config` / `set_target_folder` | Read settings (never includes keys) / change the capture folder |

**self_analyze** — if the calling model can actually see images, pass
`self_analyze=true` to `analyze_vision` / `capture_and_analyze` to analyze the
screenshot itself, without an external backend. A small image showing a
verification code is returned first; read it and call again with
`vision_check` set to that code — the screenshot is only returned if the code
matches (a vision-capability check). If you cannot read the code, fall back to
`self_analyze=false`.

## Tray menu (direct use)

- **Capture** — a whole monitor · a specific app window · drag-select a region
  · open an existing image file.
- **Analyze last image** — sends the most recent capture to the vision backend
  and shows the result.
- **Recent images** — click one to copy a ready-to-paste prompt (with the
  image path) to the clipboard (template editable in Settings).
- **Settings** — manage vision backends (add · change model name · consent ·
  default · remove), target folder, clipboard auto-copy, start at login.

> **Window capture, platform difference** — Windows lists minimized windows
> and restores them automatically before capturing; windows that refuse
> capture fall back to a monitor capture. macOS skips minimized windows
> (a ScreenCaptureKit constraint) — un-minimize first, then capture.

## Command reference

Prefix omitted: Windows `.\.venv\Scripts\vgmcp.exe …`, macOS `./.venv/bin/vgmcp …`

```bash
vgmcp                       # run the tray app + resident host
vgmcp --no-tray             # run only the host in the foreground (advanced)
vgmcp check                 # environment check with fix guidance

vgmcp provider add --type <anthropic|openai|openrouter|custom|ollama> [--model M] [--key -] [--base-url URL] [--set-default]
vgmcp provider list                        # registered backends (key/consent status)
vgmcp provider update <id> [--model M] [--key -] [--set-default]
vgmcp provider remove <id>                 # also deletes the stored key
vgmcp provider consent <id> [--revoke]     # grant / revoke external transmission

vgmcp analyze <image path> [--prompt P] [--backend ID]
vgmcp capture-analyze --target <monitor|window|region|region_interactive> [--app-name A] [--x --y --w --h] …
vgmcp autostart enable|disable|status      # start at login
```

For a `custom` backend, also pass `--base-url "https://your-endpoint/v1"`.
`--key -` always means "ask for the key with a hidden prompt".

## Troubleshooting

| Symptom | Fix |
|---|---|
| No tray / menu-bar icon | The app isn't running → run `start_win.bat` / `start_mac.command`. On Windows also check the `^` overflow |
| AI tool only shows `vgmcp_status` / "host unreachable" | Start the tray app, then retry |
| Captures black or fail (macOS) | Re-grant screen-recording permission, restart the app. Verify with `vgmcp check` |
| Captures black (Windows) | DirectX / exclusive-fullscreen apps are out of scope → capture the whole monitor |
| `AUTH_FAILED` / 401 | Wrong or expired key → `vgmcp provider update <id> --key -` |
| `consent_required` | `vgmcp provider consent <id>` (or the consent toggle in the tray menu) |
| `OLLAMA_UNAVAILABLE` | Run `ollama serve` and make sure `ollama pull llava:7b` was done |
| `command not found: python3` | Install Python from [python.org/downloads](https://www.python.org/downloads/) |

## Privacy & storage locations

- **API keys** — stored only in the OS credential store (macOS Keychain /
  Windows Credential Manager); never in plain files.
- **Settings** — `~/.config/vgmcp/config.json` (backends, target folder, …;
  *keys excluded*).
- **Screenshots** — saved to `~/Pictures/vgmcp/` by default (change via tray
  Settings → target folder).
- **External transmission** — cloud backends receive screenshots only after
  per-provider **consent**. Large images are downscaled before sending. Use
  Ollama if nothing should leave your machine. The MCP host is
  127.0.0.1-only.

## For developers

```bash
# macOS (Windows: .\.venv\Scripts\… prefix + ".[windows,dev]")
./.venv/bin/pip install -e ".[macos,dev]"
./.venv/bin/python -m pytest -q      # tests
./.venv/bin/ruff check src/ tests/   # lint
```

- Design & milestones: [`plan.md`](plan.md) · original concept:
  [`idea.md`](idea.md) · Windows port: [`windows-port-plan.md`](windows-port-plan.md) ·
  previous READMEs: [`archive/`](archive/)
- **Environment variables** — `VGMCP_LANG=ko|en` (force the UI language;
  defaults to the OS language) · `VGMCP_SERVER_URL` (host URL the adapter
  connects to, default `http://127.0.0.1:8765/mcp`; or set parts via
  `VGMCP_HOST` / `VGMCP_PORT` / `VGMCP_PATH`)
- **Tray icon** — single source of truth: `src/vgmcp/assets/aperture.svg`.
  macOS rasterizes it to PNGs cached in `~/.config/vgmcp/icons/`; Windows
  draws the same geometry in-memory with Pillow (coordinates mirrored in
  `tray/windows.py`) — if you change the SVG, update those coordinates too.

License: [MIT](../LICENSE)
