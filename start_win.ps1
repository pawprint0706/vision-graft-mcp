# Vision-Graft MCP - launch the tray app (Windows).
# Easiest: double-click start_win.bat. Or right-click this file > "Run with
# PowerShell", or run  ./start_win.ps1  in a terminal.

Set-Location -Path $PSScriptRoot
# Render Korean output correctly under Windows PowerShell 5.1 consoles.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$KO = (Get-Culture).Name -like "ko*"
function Msg($ko, $en) { if ($KO) { Write-Host $ko } else { Write-Host $en } }

if (-not (Test-Path ".\.venv\Scripts\vgmcp.exe")) {
    Msg "✗ 아직 설치되지 않았습니다. 먼저 install_win.ps1 을 실행하세요." `
        "✗ Not installed yet. Run install_win.ps1 first."
    exit 1
}

# Full restart: stop any tray/adapter instance already running (vgmcp.exe,
# vgmcp-adapter.exe, or "pythonw -m vgmcp"). Skips this script's own process.
$stopped = $false
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.ProcessId -ne $PID -and (
            $_.Name -in @("vgmcp.exe", "vgmcp-adapter.exe") -or
            ($_.CommandLine -and $_.CommandLine -match "\bvgmcp\b")
        )
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped = $true
    }
if ($stopped) {
    Msg "• 기존 실행 중인 VGMCP를 종료했습니다." "• Stopped a running VGMCP instance."
    Start-Sleep -Milliseconds 700
}

# Launch console-less (pythonw -m vgmcp) and detached so this window can close.
$pythonw = ".\.venv\Scripts\pythonw.exe"
if (Test-Path $pythonw) {
    Start-Process -FilePath $pythonw -ArgumentList "-m", "vgmcp" -WindowStyle Hidden
} else {
    Start-Process -FilePath ".\.venv\Scripts\vgmcp.exe" -WindowStyle Hidden
}

Msg "✅ VGMCP를 트레이에 실행했습니다. (작업 표시줄 오른쪽의 조리개 아이콘)" `
    "✅ VGMCP is now running in the system tray (aperture icon, bottom-right)."
Msg "이 창은 닫아도 됩니다." "You can close this window."
