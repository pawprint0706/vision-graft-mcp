#!/bin/bash
# Vision-Graft MCP — installer.
# Double-click this file in Finder, or run `./install_mac.command` in Terminal.

set -e
cd "$(dirname "$0")"

# --- language: Korean if the OS prefers Korean, else English -------------------
LOC=$(defaults read -g AppleLocale 2>/dev/null || true)
[ -z "$LOC" ] && LOC="$LANG"
case "$LOC" in ko*) KO=1 ;; *) KO=0 ;; esac
msg() { if [ "$KO" = 1 ]; then echo "$1"; else echo "$2"; fi; }

echo "════════════════════════════════════════"
msg "   Vision-Graft MCP (VGMCP) 설치" "   Vision-Graft MCP (VGMCP) installer"
echo "════════════════════════════════════════"
echo ""

# 0) stop any running instance so files update cleanly (full reinstall) --------
# Matches both ".venv/bin/vgmcp" (tray) and ".venv/bin/vgmcp-adapter" (stdio bridge).
if pkill -f "bin/vgmcp" 2>/dev/null; then
  msg "• 기존 실행 중인 VGMCP를 종료했습니다." "• Stopped a running VGMCP instance."
  sleep 1
fi

# 1) Python 3.11+ -------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  msg "✗ python3 가 설치되어 있지 않습니다." "✗ python3 is not installed."
  msg "  https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요." \
      "  Install it from https://www.python.org/downloads/ and run again."
  exit 1
fi
PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$(python3 -c 'import sys; print(1 if sys.version_info >= (3,11) else 0)')" != "1" ]; then
  msg "✗ Python 3.11 이상이 필요합니다 (현재 $PYV)." "✗ Python 3.11+ required (found $PYV)."
  msg "  https://www.python.org/downloads/ 에서 최신 버전을 설치하세요." \
      "  Install the latest from https://www.python.org/downloads/"
  exit 1
fi
msg "✓ Python $PYV 확인" "✓ Python $PYV"

# 2) virtual environment ------------------------------------------------------
if [ ! -d ".venv" ]; then
  msg "• 가상환경(.venv) 생성 중..." "• Creating virtual environment (.venv)..."
  python3 -m venv .venv
else
  msg "✓ 기존 가상환경(.venv) 사용" "✓ Using existing virtual environment (.venv)"
fi

# 3) install ------------------------------------------------------------------
msg "• 패키지 설치 중... (처음에는 수 분 걸릴 수 있습니다)" \
    "• Installing packages... (first run may take a few minutes)"
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install -e ".[macos]"

echo ""
msg "✅ 설치 완료!" "✅ Install complete!"
echo ""
if [ "$KO" = 1 ]; then
  echo "── 다음 단계 ──────────────────────────────"
  echo "1) 앱 실행:  start_mac.command 더블클릭  (또는 ./.venv/bin/vgmcp )"
  echo "2) 화면 기록 권한 허용:"
  echo "   시스템 설정 > 개인정보 보호 및 보안 > 화면 기록"
  echo "3) 비전 백엔드(API 키) 등록:"
  echo "   메뉴바 아이콘 > 설정 > 비전 백엔드 관리 > 추가…"
  echo ""
  echo "자세한 사용법은 README.md 를 참고하세요."
  echo "이 창은 닫아도 됩니다."
else
  echo "── Next steps ─────────────────────────────"
  echo "1) Start the app:  double-click start_mac.command  (or ./.venv/bin/vgmcp )"
  echo "2) Grant Screen Recording permission:"
  echo "   System Settings > Privacy & Security > Screen Recording"
  echo "3) Register a vision backend (API key):"
  echo "   menu-bar icon > Settings > Manage vision backends > Add…"
  echo ""
  echo "See docs/README.en.md for full instructions."
  echo "You can close this window."
fi
