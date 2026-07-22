#!/bin/bash
# Vision-Graft MCP — launch the menu-bar app.
# Double-click this file in Finder, or run `./start_mac.command` in Terminal.

cd "$(dirname "$0")"

LOC=$(defaults read -g AppleLocale 2>/dev/null || true)
[ -z "$LOC" ] && LOC="$LANG"
case "$LOC" in ko*) KO=1 ;; *) KO=0 ;; esac
msg() { if [ "$KO" = 1 ]; then echo "$1"; else echo "$2"; fi; }

if [ ! -x ".venv/bin/vgmcp" ]; then
  msg "✗ 아직 설치되지 않았습니다. 먼저 install_mac.command 를 실행하세요." \
      "✗ Not installed yet. Run install_mac.command first."
  exit 1
fi

# Full restart: stop any tray/adapter instance already running (ignore if none).
# Matches both ".venv/bin/vgmcp" (tray) and ".venv/bin/vgmcp-adapter" (stdio bridge).
if pkill -f "bin/vgmcp" 2>/dev/null; then
  msg "• 기존 실행 중인 VGMCP를 종료했습니다." "• Stopped a running VGMCP instance."
  sleep 1
fi

# Launch detached so this Terminal window can be closed.
nohup ./.venv/bin/vgmcp >/dev/null 2>&1 &
msg "✅ VGMCP를 메뉴바에 실행했습니다. (화면 오른쪽 위의 조리개 아이콘)" \
    "✅ VGMCP is now running in the menu bar (camera icon, top-right)."
msg "이 창은 닫아도 됩니다." "You can close this window."
