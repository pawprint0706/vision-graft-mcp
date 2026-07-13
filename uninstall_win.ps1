# Vision-Graft MCP - uninstaller (Windows).
# Easiest: double-click uninstall_win.bat. Or right-click this file > "Run with
# PowerShell", or run  ./uninstall_win.ps1  in a terminal. If blocked by
# execution policy:  powershell -ExecutionPolicy Bypass -File .\uninstall_win.ps1
# Safe to re-run. Reverses what install_win.ps1 created and optionally removes
# user data. Does NOT delete the repository folder itself.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
# Render Korean output correctly under Windows PowerShell 5.1 consoles.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# --- language: Korean if the OS prefers Korean, else English -------------------
$KO = (Get-Culture).Name -like "ko*"
function Msg($ko, $en) { if ($KO) { Write-Host $ko } else { Write-Host $en } }
function Ask($ko, $en) {
    if ($KO) { Write-Host "$ko [y/N] " -NoNewline } else { Write-Host "$en [y/N] " -NoNewline }
    $a = Read-Host
    if ($null -eq $a -or $a.Trim() -eq "") { return $false }
    $a.Trim() -match '^(y|yes)$'
}

Write-Host "========================================"
Msg "   Vision-Graft MCP (VGMCP) 제거" "   Vision-Graft MCP (VGMCP) uninstaller"
Write-Host "========================================"
Write-Host ""

# 0) stop any running instance so files can be removed ------------------------
# Matches vgmcp.exe, vgmcp-adapter.exe, or "pythonw -m vgmcp"; skips this script.
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
    Msg "• 실행 중인 VGMCP를 종료했습니다." "• Stopped a running VGMCP instance."
    Start-Sleep -Milliseconds 700
}

# 1) disable autostart (Run registry key) -------------------------------------
# A stale Run value would try to launch a deleted executable at next login, so
# this is always done (not optional).
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runVal = "VGMCP"
if (Test-Path $runKey) {
    $existing = $null
    try { $existing = (Get-ItemProperty -Path $runKey -Name $runVal -ErrorAction Stop).$runVal } catch {}
    if ($existing) {
        Remove-ItemProperty -Path $runKey -Name $runVal -ErrorAction SilentlyContinue
        Msg "• 로그인 시 자동 시작(레지스트리)을 제거했습니다." `
            "• Removed the start-at-login entry (registry)."
    }
}

# 2) optional: remove user data (config + API keys) ---------------------------
# Settings live at ~\.config\vgmcp\ (config.json). API keys are in the Windows
# Credential Manager under the "vgmcp" service (stored by keyring, plan §7.6).
# keyring stores the first key as TargetName="vgmcp" and subsequent keys as
# TargetName="provider:<id>@vgmcp" (compound name).
$configRoot = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $HOME ".config" }
$configDir = Join-Path $configRoot "vgmcp"
if (Ask "설정과 API 키(자격 증명 관리자)도 삭제할까요?" `
        "Also remove settings and API keys (Credential Manager)?") {
    # Use the CLI to remove every provider — each removal also deletes its
    # stored key (credentials.delete_key → keyring.delete_password).
    $vgmcp = ".\.venv\Scripts\vgmcp.exe"
    if (Test-Path $vgmcp) {
        try {
            $list = & $vgmcp provider list 2>$null | ConvertFrom-Json
            foreach ($p in $list.providers) {
                & $vgmcp provider remove $p.id 2>$null | Out-Null
            }
        } catch {}
    }
    # Best-effort: delete any lingering Windows Credential Manager entries
    # whose target contains "vgmcp" (covers both simple and compound targets).
    try {
        (& cmdkey /list 2>$null) | ForEach-Object {
            # The label before ':' is localized (for example Target / 대상),
            # so match by structure and the VGMCP target name instead.
            if ($_ -match '^\s*[^:]+:\s*(.+vgmcp.*)$') {
                $tgt = $Matches[1].Trim()
                if ($tgt -match 'vgmcp') {
                    & cmdkey /delete:"$tgt" 2>$null | Out-Null
                }
            }
        }
    } catch {}
    if (Test-Path $configDir) {
        Remove-Item -Path $configDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Msg "• 설정과 자격 증명을 삭제했습니다." "• Removed settings and credentials."
}

# 3) optional: remove screenshots --------------------------------------------
$shotDir = Join-Path $HOME "Pictures\vgmcp"
if ((Test-Path $shotDir) -and (Ask "캡처한 스크린샷도 삭제할까요? ($shotDir)" `
                                     "Also remove captured screenshots? ($shotDir)")) {
    Remove-Item -Path $shotDir -Recurse -Force -ErrorAction SilentlyContinue
    Msg "• 스크린샷 폴더를 삭제했습니다." "• Removed the screenshots folder."
}

# 4) remove the virtual environment (the main install artifact) ---------------
# install_win.ps1 creates .venv and runs `pip install -e ".[windows]"`; this
# reverses both in one step (the editable install lives inside .venv).
if (Test-Path ".venv") {
    Remove-Item -Path ".venv" -Recurse -Force -ErrorAction SilentlyContinue
    Msg "• 가상환경(.venv)을 삭제했습니다." "• Removed the virtual environment (.venv)."
} else {
    Msg "• 가상환경(.venv)이 없습니다 (이미 제거됨)." `
        "• No virtual environment (.venv) found (already removed)."
}

Write-Host ""
Msg "✅ 제거 완료!" "✅ Uninstall complete!"
Write-Host ""
if ($KO) {
    Write-Host "── 수동으로 삭제해야 할 항목 ──────────────"
    Write-Host "• AI 도구 MCP 등록:"
    Write-Host "    Claude Code:     claude mcp remove vgmcp"
    Write-Host "    Cursor:          ~/.cursor/mcp.json 에서 `"vgmcp`" 항목 제거"
    Write-Host "    Claude Desktop:  %APPDATA%\Claude\claude_desktop_config.json"
    Write-Host "• 타겟 폴더를 변경했다면 해당 폴더의 캡처 파일은 유지됩니다."
    Write-Host ""
    Write-Host "이 저장소 폴더 자체는 유지됩니다. 완전히 지우려면 폴더를 삭제하세요."
} else {
    Write-Host "── Remaining manual steps ────────────────"
    Write-Host "• AI tool MCP registration:"
    Write-Host "    Claude Code:     claude mcp remove vgmcp"
    Write-Host "    Cursor:          remove the `"vgmcp`" entry from ~/.cursor/mcp.json"
    Write-Host "    Claude Desktop:  %APPDATA%\Claude\claude_desktop_config.json"
    Write-Host "• Captures in a custom target folder are kept."
    Write-Host ""
    Write-Host "The repository folder itself is kept. Delete it to remove everything."
}
Write-Host ""
Msg "이 창은 닫아도 됩니다." "You can close this window."
