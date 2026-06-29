@echo off
REM Vision-Graft MCP - installer (double-click friendly).
REM Wraps install_win.ps1 so a double-click "just works" regardless of the
REM default .ps1 file association or the PowerShell execution policy.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_win.ps1"
echo.
pause
