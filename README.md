# Vision-Graft MCP (VGMCP)

**English** · [한국어](README.ko.md)

> ⚠️ **Work in progress.** This project is still under active development, and
> this README will be revised again. Steps, commands, and behavior may change.



Give a "blind" AI coding model an **eye**. Many fast or local LLMs can't see
images — they only read your HTML/CSS/JSX, so they can't tell when a button is
cut off or two elements overlap. VGMCP captures your screen, sends it to a
vision-capable model, and hands the AI back a written report it *can* read — so
it can actually debug visual bugs.

It works two ways at once:

- **The AI uses it** through the [MCP](https://modelcontextprotocol.io) standard
  (in Cursor, Claude Desktop, oh-my-pi, etc.).
- **You use it** from a small **menu-bar icon (macOS) / system-tray icon
  (Windows)** (capture a screen/window/region, analyze the last image, copy a
  ready-to-paste prompt).

> Platform: **macOS 14 (Sonoma) or newer**, or **Windows 10/11**.

---

## Table of contents

1. [How it works (30-second version)](#how-it-works)
2. [Before you start](#before-you-start)
3. [Step 1 — Install](#step-1--install)
4. [Step 2 — Add a vision provider (API key)](#step-2--add-a-vision-provider-api-key)
5. [Step 3 — Grant screen-recording permission](#step-3--grant-screen-recording-permission)
6. [Step 4 — Start the app](#step-4--start-the-app)
7. [Step 5 — Connect your AI tool (MCP)](#step-5--connect-your-ai-tool-mcp)
8. [Using it every day](#using-it-every-day)
9. [Command reference](#command-reference)
10. [Troubleshooting](#troubleshooting)
11. [Privacy & where things are stored](#privacy--where-things-are-stored)
12. [For developers](#for-developers)

---

## How it works

```
Your AI tool (Cursor / Claude / oh-my-pi)
        │  asks for a screenshot + analysis (MCP)
        ▼
  vgmcp-adapter  ── talks to ──▶  VGMCP app (menu-bar, always running)
                                   • captures the screen
                                   • sends it to your vision model
                                   • returns a written report
        ▲
        └─ You can also drive the same thing from the menu-bar icon.
```

The **menu-bar app must be running** for the AI side to work — it's the piece
that holds the camera and the settings.

---

## Before you start

For setup you'll use a terminal — **Terminal** on macOS (Applications → Utilities
→ Terminal), **PowerShell** on Windows (Start → type "PowerShell"). You only copy
and paste a few lines. (Most steps below also have a **double-click** option, so
you can skip the terminal entirely.)

**Check you have Python 3.11 or newer:**

```bash
python3 --version    # macOS
python --version     # Windows
```

- If it prints `Python 3.11.x` or higher → you're good.
- If it's older or "command not found" → install the latest Python from
  [python.org/downloads](https://www.python.org/downloads/) (macOS + Homebrew:
  `brew install python`; on **Windows** tick **"Add Python to PATH"** in the
  installer), then re-check.

You'll also need an **API key** from one vision provider (pick one):

| Provider | Where to get a key | Notes |
|---|---|---|
| **OpenRouter** | <https://openrouter.ai/keys> | One key, many models. Good default. |
| **Anthropic (Claude)** | <https://console.anthropic.com/> | |
| **OpenAI (GPT-4o)** | <https://platform.openai.com/api-keys> | |
| **Ollama (local)** | *no key* — <https://ollama.com> | Runs on your own computer, free, nothing leaves it. |

---

## Step 1 — Install

After cloning or downloading & unzipping the project:

### macOS

**Easiest — double-click `install_mac.command`** in the project folder (Finder).
A Terminal window runs the installer (it creates an isolated Python environment
and installs VGMCP). When it prints **"✅ 설치 완료 / Install complete"**, you're
done.

> If macOS won't run it (right-click only, or "permission denied"): right-click
> `install_mac.command` → **Open** (then confirm), or in Terminal run
> `chmod +x install_mac.command && ./install_mac.command`.

Terminal alternative:

```bash
cd <the project folder>
./install_mac.command
# fully manual:
python3 -m venv .venv && .venv/bin/pip install -e ".[macos]"
```

### Windows

**Easiest — double-click `install_win.bat`** in the project folder. A PowerShell
window runs the installer; when it prints **"✅ 설치 완료 / Install complete"**,
you're done. (The `.bat` handles the PowerShell execution-policy prompt for you.)

PowerShell alternative:

```powershell
cd <the project folder>
.\install_win.ps1     # if blocked: powershell -ExecutionPolicy Bypass -File .\install_win.ps1
# fully manual:
python -m venv .venv ; .\.venv\Scripts\pip install -e ".[windows]"
```

> **📌 Command paths in the rest of this guide** are written in the macOS form
> `.venv/bin/vgmcp …`. **On Windows, use `.venv\Scripts\vgmcp.exe …`** instead
> (and `python` rather than `python3`). Everything after the prefix is identical.

---

## Step 2 — Add a vision provider (API key)

You can do this **two ways** — use whichever you prefer:

> **🖱️ Prefer clicking? Use the menu bar (no Terminal needed).**
> Start the app first ([Step 4](#step-4--start-the-app)), then open the menu-bar
> icon → **설정 / Settings → 비전 백엔드 관리 / Manage vision backends →
> 추가… / Add…**. It asks you, one box at a time, for the provider type, a name,
> the model, (for `custom`) the endpoint URL, and the API key (the key field is
> masked). Consent is the **외부 전송 동의 / Allow external transmission** item
> in that same submenu, and you can set the default there too. If you go this
> route, you can skip the commands below.

**⌨️ Or use the Terminal.** Register the provider you chose. Using `--key -`
makes the Terminal ask for the key with a **hidden prompt**, so your secret never
shows on screen or in history.

**OpenRouter (recommended):**

```bash
.venv/bin/vgmcp provider add --type openrouter --model "openai/gpt-4o" --key - --set-default
.venv/bin/vgmcp provider consent openrouter
```

**Anthropic (Claude):**

```bash
.venv/bin/vgmcp provider add --type anthropic --key - --set-default
.venv/bin/vgmcp provider consent anthropic
```

**OpenAI:**

```bash
.venv/bin/vgmcp provider add --type openai --key - --set-default
.venv/bin/vgmcp provider consent openai
```

**Ollama (local, no key, nothing sent to the cloud):**

```bash
# First install Ollama from https://ollama.com and pull a vision model:
ollama pull llava:7b
.venv/bin/vgmcp provider add --type ollama --model "llava:7b" --set-default
# No consent needed — it never leaves your computer.
```

> **Choosing a local model.** Use a **non-reasoning** vision model that fits your
> **VRAM** — reasoning/thinking VLMs (e.g. `qwen3-vl`) tend to spend the whole
> token budget "thinking" and return an empty/unstable answer, so they're not
> recommended here. For an **8 GB** GPU, **`llava:7b`** (~4.7 GB) is the
> recommended pick. With less VRAM try a smaller model (e.g. `moondream`); with
> more, a larger one. Note that small local models are handy for quick checks but
> are far less accurate than a cloud model — use a cloud provider when you need a
> precise analysis.

The `consent` line is a one-time **"yes, you may send my screenshots to this
cloud service"** confirmation. (Ollama doesn't need it.)

Check it worked:

```bash
.venv/bin/vgmcp provider list
```

You should see your provider with `"has_key": true` and `"consented": true`.

---

## Step 3 — Grant screen-recording permission

### Windows

Nothing to do — Windows needs no special screen-capture permission. Skip to
[Step 4](#step-4--start-the-app). (You can still verify with
`.venv\Scripts\vgmcp.exe check`.)

### macOS

macOS must allow VGMCP to see the screen.

1. Open **System Settings → Privacy & Security → Screen Recording**.
2. Turn on the toggle for your **Terminal** (and later, the VGMCP app).
3. If macOS asks you to quit & reopen the app, do so.

You only do this once. (On macOS, the app that *launches* VGMCP is the one that
needs permission — usually Terminal during setup.)

Verify everything is ready:

```bash
.venv/bin/vgmcp check
```

If it prints a list of "missing" items, follow each `guide`/`install_command`.
When fully set up it says the environment is OK.

---

## Step 4 — Start the app

- **macOS:** double-click **`start_mac.command`** (or run `.venv/bin/vgmcp`). A
  small **icon appears in the menu bar** (top-right of the screen).
- **Windows:** double-click **`start_win.bat`** (or run
  `.venv\Scripts\vgmcp.exe`). A small **icon appears in the system tray**
  (bottom-right by the clock — you may need to click the **^** overflow arrow).
  It launches hidden, so you can close the window.

Then, on either platform:

- 🟢 green / **white·black** (Windows, adapts to the taskbar) = ready ·
  🟡 yellow = works but something optional is missing ·
  🔴 red = needs attention (click it for guidance).
- On first launch you'll see a short welcome notice — read it and click OK.
- A single **left-click** (or right-click) opens the menu.

Leave it running. To stop it, click the icon → **종료 / Quit**.

**Want it to start automatically every time you log in?**

```bash
.venv/bin/vgmcp autostart enable
```

(Or toggle **설정 → 로그인 시 자동 시작 / Settings → Start at login** in the menu.)

---

## Step 5 — Connect your AI tool (MCP)

Your AI tool talks to VGMCP through a tiny helper called the **adapter**. You
register it once in your tool's MCP settings. Use the **full path** to the
adapter (replace the path below with your project location):

```json
{
  "mcpServers": {
    "vgmcp": {
      "command": "/Users/yourname/Projects/vision-graft-mcp/.venv/bin/vgmcp-adapter"
    }
  }
}
```

On **Windows** the command is the `.exe` under `Scripts` (use double backslashes
in JSON), e.g.:

```json
{ "mcpServers": { "vgmcp": {
  "command": "C:\\Users\\yourname\\Projects\\vision-graft-mcp\\.venv\\Scripts\\vgmcp-adapter.exe"
} } }
```

Find your exact path with:

```bash
echo "$(pwd)/.venv/bin/vgmcp-adapter"          # macOS
```
```powershell
"$(Get-Location)\.venv\Scripts\vgmcp-adapter.exe"   # Windows
```

Where this JSON goes depends on the tool:

- **Cursor:** `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` in your project.
- **Claude Desktop (macOS):** `~/Library/Application Support/Claude/claude_desktop_config.json`.
- **Claude Desktop (Windows):** `%APPDATA%\Claude\claude_desktop_config.json`.
- **oh-my-pi / others:** wherever the tool lists "MCP servers".

Restart the AI tool after editing. It should now show VGMCP's tools (like
`take_screenshot` and `analyze_vision`).

> **Important:** the menu-bar app from Step 4 must be running, otherwise the
> adapter politely reports that the app is off and asks you to start it.

---

## Using it every day

**Let the AI do it.** Just ask your coding model things like:

> "Run the app, take a screenshot, and check if the layout is broken."

It will call `take_screenshot` → `analyze_vision` and use the written report to
fix the CSS — even though it can't see images itself.

**Or do it yourself from the menu-bar (macOS) / system-tray (Windows) icon:**

- **캡처 / Capture** → whole monitor, a specific window, or **drag-select a
  region**, or open an existing image file.
  - *Platform note — minimized windows:* on **Windows** the app-window list
    includes minimized windows and restores them automatically before capturing.
    On **macOS** minimized windows are skipped (ScreenCaptureKit has no rendered
    surface for them, and restoring another app's window would require a separate
    Accessibility permission), so un-minimize the window first to capture it.
- **마지막 이미지 분석 / Analyze last image** → sends the most recent capture to
  your vision model and shows a summary.
- **최근 이미지 / Recent images** → click one to copy a ready-to-paste prompt
  (with the image path) to your clipboard. Paste it into your AI tool.

**Quick test from Terminal** (no AI tool needed):

```bash
.venv/bin/vgmcp capture-analyze --target region --x 0 --y 0 --w 800 --h 500
```

This captures part of your screen and prints the vision model's report.

---

## Command reference

```bash
# App / host
vgmcp                      # start the menu-bar app + background host
vgmcp --no-tray            # run only the host, in the foreground (advanced)
vgmcp check                # check the environment and print what's missing

# Vision providers
vgmcp provider add --type <anthropic|openai|openrouter|custom|ollama> [--model M] [--key -] [--set-default]
vgmcp provider list                         # show providers (key/consent status)
vgmcp provider update <id> [--model M] [--key -] [--set-default]
vgmcp provider remove <id>                  # also deletes its stored key
vgmcp provider consent <id> [--revoke]      # allow/deny sending screenshots to the cloud

# Run the real vision loop
vgmcp capture-analyze --target monitor                          # capture screen + analyze
vgmcp capture-analyze --target window --app-name "Safari"       # a specific app window
vgmcp capture-analyze --target region --x 100 --y 100 --w 600 --h 400
vgmcp analyze /path/to/image.png                                # analyze an existing image

# Start at login
vgmcp autostart enable | disable | status
```

For a `custom` (self-hosted / gateway) provider, also pass
`--base-url "https://your-endpoint/v1"`. `--key -` always means "ask me for the
key with a hidden prompt".

---

## Troubleshooting

**The menu-bar / system-tray icon isn't there.**
The app isn't running. Run `.venv/bin/vgmcp` (macOS) or `.venv\Scripts\vgmcp.exe`
(Windows). On Windows, check the **^** system-tray overflow. (Closing the
launching terminal can stop it — enable autostart, or use the double-click
launcher.)

**Captures are black or fail.**
- **macOS:** screen-recording permission is missing or stale. Redo
  [Step 3](#step-3--grant-screen-recording-permission), then quit & restart the
  app. Run `.venv/bin/vgmcp check` to confirm.
- **Windows:** no permission is needed; a black frame usually means a
  DirectX/exclusive-fullscreen app (out of scope). Capture the **whole monitor**
  instead, or use a normal app window.

**The AI tool says the host is unreachable.**
Start the menu-bar app (`.venv/bin/vgmcp`) — the adapter needs it running.

**`AUTH_FAILED` / 401 from the vision model.**
Your API key is wrong or expired. Re-store it:
`.venv/bin/vgmcp provider update <id> --key -`

**`consent_required`.**
You haven't approved sending screenshots to that cloud provider yet:
`.venv/bin/vgmcp provider consent <id>` (or the menu toggle). Local Ollama never
needs this.

**`OLLAMA_UNAVAILABLE`.**
Start Ollama (`ollama serve`) and make sure the model is pulled
(`ollama pull llava:7b`).

**`command not found: python3`.**
Install Python from [python.org/downloads](https://www.python.org/downloads/).

---

## Privacy & where things are stored

- **API keys** are stored in the OS credential store — **macOS Keychain** /
  **Windows Credential Manager** — never in plain files.
- **Settings** live in `~/.config/vgmcp/config.json` (macOS) /
  `%USERPROFILE%\.config\vgmcp\config.json` (Windows) — providers, target folder,
  preferences, but *not* keys.
- **Screenshots** are saved to `~/Pictures/vgmcp/` (macOS) /
  `%USERPROFILE%\Pictures\vgmcp\` (Windows) by default (change it in
  Settings → Target folder).
- **Cloud providers** receive your screenshots only after you give **consent**
  per provider. Large images are scaled down before sending; small ones are sent
  as-is. Prefer **Ollama** if you want nothing to leave your computer.

---

## For developers

```bash
# macOS
.venv/bin/pip install -e ".[macos,dev]"
.venv/bin/python -m pytest -q      # run tests
.venv/bin/ruff check src/ tests/   # lint
```
```powershell
# Windows
.\.venv\Scripts\pip install -e ".[windows,dev]"
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\ruff check src/ tests/
```

- **Language:** the app, installer, and launcher show **Korean if the OS prefers
  Korean, otherwise English**. Force it with `VGMCP_LANG=ko` or `VGMCP_LANG=en`.
- **Custom tray icon:** the icon comes from a single SVG at
  `src/vgmcp/assets/aperture.svg` (the source of truth). On **macOS** it's
  rasterized to cached PNGs in `~/.config/vgmcp/icons/` (delete to regenerate);
  the normal state is a black **template** image (auto black/white by light/dark)
  plus **amber/red** for warning/error. On **Windows** the same geometry is drawn
  with Pillow in-memory (coords mirror the SVG in `tray/windows.py`); the OK state
  adapts to the taskbar theme (white/black) with amber/red for warning/error. If
  you change `aperture.svg`, update the Windows coordinates to match.
- Architecture, milestones, and the full spec: [`docs/plan.md`](docs/plan.md);
  original concept: [`docs/idea.md`](docs/idea.md).
- The tray app hosts a loopback MCP server (`127.0.0.1:8765`) holding the shared
  core (capture / vision / clipboard / environment). MCP clients connect via the
  thin `vgmcp-adapter`, which proxies to it — so both the user (tray) and the AI
  (MCP) drive the same core, target folder, and config.
- Override the adapter's target with `VGMCP_SERVER_URL` (or `VGMCP_HOST` /
  `VGMCP_PORT`) if you run the host somewhere non-default.

Requires Python ≥ 3.11. macOS target is 14 (Sonoma)+ (ScreenCaptureKit);
Windows target is 10/11 (mss + Win32, pystray tray).
