#!/bin/bash
# Vision-Graft MCP — uninstaller.
# Double-click this file in Finder, or run `./uninstall_mac.command` in Terminal.
# Safe to re-run. Reverses what install_mac.command created and optionally
# removes user data. Does NOT delete the repository folder itself.

set -e
cd "$(dirname "$0")"

# --- language: Korean if the OS prefers Korean, else English -------------------
LOC=$(defaults read -g AppleLocale 2>/dev/null || true)
[ -z "$LOC" ] && LOC="$LANG"
case "$LOC" in ko*) KO=1 ;; *) KO=0 ;; esac
msg() { if [ "$KO" = 1 ]; then echo "$1"; else echo "$2"; fi; }

# yes/no prompt (default: No). Returns 0 = yes, 1 = no.
ask() {
  if [ "$KO" = 1 ]; then read -r -p "$1 [y/N] " a; else read -r -p "$2 [y/N] " a; fi
  case "$a" in y|Y|yes|YES|Yes) return 0 ;; *) return 1 ;; esac
}

echo "════════════════════════════════════════"
msg "   Vision-Graft MCP (VGMCP) 제거" "   Vision-Graft MCP (VGMCP) uninstaller"
echo "════════════════════════════════════════"
echo ""

# 0) stop any running instance so files can be removed -------------------------
# Matches both ".venv/bin/vgmcp" (tray) and ".venv/bin/vgmcp-adapter" (stdio bridge).
if pkill -f "bin/vgmcp" 2>/dev/null; then
  msg "• 실행 중인 VGMCP를 종료했습니다." "• Stopped a running VGMCP instance."
  sleep 1
fi

# 1) disable autostart (LaunchAgent) -------------------------------------------
# A stale LaunchAgent would try to launch a deleted executable at next login, so
# this is always done (not optional). Uses the CLI when available, then removes
# the plist directly as a fallback.
PLIST="$HOME/Library/LaunchAgents/com.vgmcp.tray.plist"
if [ -x "./.venv/bin/vgmcp" ]; then
  ./.venv/bin/vgmcp autostart disable >/dev/null 2>&1 || true
fi
if [ -f "$PLIST" ]; then
  launchctl unload -w "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  msg "• 로그인 시 자동 시작(LaunchAgent)을 제거했습니다." \
      "• Removed the start-at-login entry (LaunchAgent)."
fi

# 2) optional: remove user data (config + API keys) ---------------------------
# Settings live at ~/.config/vgmcp/ (config.json, icon cache). API keys are in
# the macOS Keychain under the "vgmcp" service (stored by keyring, plan §7.6).
CONFIG_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG_DIR="$CONFIG_ROOT/vgmcp"
if ask "설정과 API 키(키체인)도 삭제할까요?" \
       "Also remove settings and API keys (keychain)?"; then
  # Use the CLI to remove every provider — each removal also deletes its
  # keychain key (credentials.delete_key → keyring.delete_password).
  if [ -x "./.venv/bin/vgmcp" ]; then
    while IFS= read -r pid; do
      [ -z "$pid" ] && continue
      ./.venv/bin/vgmcp provider remove "$pid" >/dev/null 2>&1 || true
    done < <(./.venv/bin/vgmcp provider list 2>/dev/null \
          | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    for p in d.get("providers", []):
        print(p["id"])
except Exception:
    pass
          ' 2>/dev/null || true)
  fi
  # Best-effort sweep of any remaining keychain entries for the "vgmcp" service.
  # Loops because there may be one generic-password per provider key_ref.
  while security delete-generic-password -s vgmcp >/dev/null 2>&1; do :; done
  rm -rf "$CONFIG_DIR"
  msg "• 설정과 키체인 키를 삭제했습니다." "• Removed settings and keychain keys."
fi

# 3) optional: remove screenshots ---------------------------------------------
SHOT_DIR="$HOME/Pictures/vgmcp"
if [ -d "$SHOT_DIR" ] && ask "캡처한 스크린샷도 삭제할까요? ($SHOT_DIR)" \
                              "Also remove captured screenshots? ($SHOT_DIR)"; then
  rm -rf "$SHOT_DIR"
  msg "• 스크린샷 폴더를 삭제했습니다." "• Removed the screenshots folder."
fi

# 4) remove the virtual environment (the main install artifact) ---------------
# install_mac.command creates .venv and runs `pip install -e ".[macos]"`; this
# reverses both in one step (the editable install lives inside .venv).
if [ -d ".venv" ]; then
  rm -rf .venv
  msg "• 가상환경(.venv)을 삭제했습니다." "• Removed the virtual environment (.venv)."
else
  msg "• 가상환경(.venv)이 없습니다 (이미 제거됨)." \
      "• No virtual environment (.venv) found (already removed)."
fi

echo ""
msg "✅ 제거 완료!" "✅ Uninstall complete!"
echo ""
if [ "$KO" = 1 ]; then
  echo "── 수동으로 삭제해야 할 항목 ──────────────"
  echo "• AI 도구 MCP 등록:"
  echo "    Claude Code:     claude mcp remove vgmcp"
  echo "    Cursor:          ~/.cursor/mcp.json 에서 \"vgmcp\" 항목 제거"
  echo "    Claude Desktop:  ~/Library/Application Support/Claude/claude_desktop_config.json"
  echo "• 화면 기록 권한(선택): 시스템 설정 > 개인정보 보호 및 보안 > 화면 기록"
  echo "• 타겟 폴더를 변경했다면 해당 폴더의 캡처 파일은 유지됩니다."
  echo ""
  echo "이 저장소 폴더 자체는 유지됩니다. 완전히 지우려면 폴더를 삭제하세요."
else
  echo "── Remaining manual steps ────────────────"
  echo "• AI tool MCP registration:"
  echo "    Claude Code:     claude mcp remove vgmcp"
  echo "    Cursor:          remove the \"vgmcp\" entry from ~/.cursor/mcp.json"
  echo "    Claude Desktop:  ~/Library/Application Support/Claude/claude_desktop_config.json"
  echo "• Screen Recording permission (optional): System Settings > Privacy & Security > Screen Recording"
  echo "• Captures in a custom target folder are kept."
  echo ""
  echo "The repository folder itself is kept. Delete it to remove everything."
fi
echo ""
msg "이 창은 닫아도 됩니다." "You can close this window."
