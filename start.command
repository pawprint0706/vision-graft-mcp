#!/bin/bash
# Vision-Graft MCP — launch the menu-bar app.
# Double-click this file in Finder, or run `./start.command` in Terminal.

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/vgmcp" ]; then
  echo "✗ 아직 설치되지 않았습니다. 먼저 install.command 를 실행하세요."
  exit 1
fi

# Launch detached so this Terminal window can be closed.
nohup ./.venv/bin/vgmcp >/dev/null 2>&1 &
echo "✅ VGMCP를 메뉴바에 실행했습니다. (화면 오른쪽 위의 조리개 아이콘)"
echo "이 창은 닫아도 됩니다."
