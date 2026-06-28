#!/bin/bash
# Vision-Graft MCP — installer.
# Double-click this file in Finder, or run `./install.command` in Terminal.

set -e
cd "$(dirname "$0")"

echo "════════════════════════════════════════"
echo "   Vision-Graft MCP (VGMCP) 설치"
echo "════════════════════════════════════════"
echo ""

# 1) Python 3.11+ 확인 ----------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ python3 가 설치되어 있지 않습니다."
  echo "  https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요."
  exit 1
fi
PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$(python3 -c 'import sys; print(1 if sys.version_info >= (3,11) else 0)')" != "1" ]; then
  echo "✗ Python 3.11 이상이 필요합니다 (현재 $PYV)."
  echo "  https://www.python.org/downloads/ 에서 최신 버전을 설치하세요."
  exit 1
fi
echo "✓ Python $PYV 확인"

# 2) 가상환경 생성 --------------------------------------------------------------
if [ ! -d ".venv" ]; then
  echo "• 가상환경(.venv) 생성 중..."
  python3 -m venv .venv
else
  echo "✓ 기존 가상환경(.venv) 사용"
fi

# 3) 패키지 설치 ----------------------------------------------------------------
echo "• 패키지 설치 중... (처음에는 수 분 걸릴 수 있습니다)"
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install -e ".[macos]"

echo ""
echo "✅ 설치 완료!"
echo ""
echo "── 다음 단계 ──────────────────────────────"
echo "1) 앱 실행:  start.command 더블클릭"
echo "             (또는 터미널에서  ./.venv/bin/vgmcp )"
echo "2) 화면 기록 권한 허용:"
echo "   시스템 설정 > 개인정보 보호 및 보안 > 화면 기록"
echo "3) 비전 백엔드(API 키) 등록:"
echo "   메뉴바 아이콘 > 설정 > 비전 백엔드 관리 > 추가…"
echo "   (또는 터미널에서:"
echo "    ./.venv/bin/vgmcp provider add --type openrouter --model \"openai/gpt-4o\" --key - --set-default )"
echo ""
echo "자세한 사용법은 README.md / README.ko.md 를 참고하세요."
echo "이 창은 닫아도 됩니다."
