# Vision-Graft MCP - installer (Windows).
# Easiest: double-click install_win.bat. Or right-click this file > "Run with
# PowerShell", or run  ./install_win.ps1  in a terminal. If blocked by execution
# policy:  powershell -ExecutionPolicy Bypass -File .\install_win.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
# Render Korean output correctly under Windows PowerShell 5.1 consoles.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# --- language: Korean if the OS prefers Korean, else English -------------------
$KO = (Get-Culture).Name -like "ko*"
function Msg($ko, $en) { if ($KO) { Write-Host $ko } else { Write-Host $en } }

Write-Host "========================================"
Msg "   Vision-Graft MCP (VGMCP) 설치" "   Vision-Graft MCP (VGMCP) installer"
Write-Host "========================================"
Write-Host ""

# 1) Python 3.11+ -------------------------------------------------------------
$python = $null
foreach ($cmd in @("python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $python = $cmd; break }
}
if (-not $python) {
    Msg "✗ Python 이 설치되어 있지 않습니다." "✗ Python is not installed."
    Msg "  https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요. ('Add to PATH' 체크)" `
        "  Install it from https://www.python.org/downloads/ and run again (check 'Add to PATH')."
    exit 1
}
$pyv = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$ok = & $python -c "import sys; print(1 if sys.version_info >= (3,11) else 0)"
if ($ok.Trim() -ne "1") {
    Msg "✗ Python 3.11 이상이 필요합니다 (현재 $pyv)." "✗ Python 3.11+ required (found $pyv)."
    exit 1
}
Msg "✓ Python $pyv 확인" "✓ Python $pyv"

# 2) virtual environment ------------------------------------------------------
if (-not (Test-Path ".venv")) {
    Msg "• 가상환경(.venv) 생성 중..." "• Creating virtual environment (.venv)..."
    & $python -m venv .venv
} else {
    Msg "✓ 기존 가상환경(.venv) 사용" "✓ Using existing virtual environment (.venv)"
}

# 3) install ------------------------------------------------------------------
Msg "• 패키지 설치 중... (처음에는 수 분 걸릴 수 있습니다)" `
    "• Installing packages... (first run may take a few minutes)"
& ".\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e ".[windows]"

Write-Host ""
Msg "✅ 설치 완료!" "✅ Install complete!"
Write-Host ""
if ($KO) {
    Write-Host "── 다음 단계 ──────────────────────────────"
    Write-Host "1) 앱 실행:  start_win.bat 더블클릭  (또는 .\.venv\Scripts\vgmcp.exe )"
    Write-Host "2) 비전 백엔드(API 키) 등록:"
    Write-Host "   트레이 아이콘 > 설정 > 비전 백엔드 관리 > 추가…"
    Write-Host ""
    Write-Host "자세한 사용법은 README.ko.md 를 참고하세요."
} else {
    Write-Host "── Next steps ─────────────────────────────"
    Write-Host "1) Start the app:  double-click start_win.bat  (or .\.venv\Scripts\vgmcp.exe )"
    Write-Host "2) Register a vision backend (API key):"
    Write-Host "   tray icon > Settings > Manage vision backends > Add…"
    Write-Host ""
    Write-Host "See README.md for full instructions."
}
