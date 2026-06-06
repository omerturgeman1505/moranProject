@echo off
REM Claude Code Remote Control launcher for the Moran job dashboard project.
REM Run this once on the PC. Then control everything from your phone.

setlocal
set "NODEDIR=C:\Users\omert\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.16.0-win-x64"
set "PATH=%NODEDIR%;%PATH%"
cd /d "%~dp0"

echo ============================================================
echo  Step 1/2: Log in to Claude (browser will open).
echo  Use your claude.ai account (Pro / Max / Team / Enterprise).
echo ============================================================
call claude auth login

echo.
echo ============================================================
echo  Step 2/2: Starting Remote Control session.
echo  A QR code will appear -- scan it with your phone camera,
echo  or open https://claude.ai/code in any browser.
echo  Press the spacebar inside this window if the QR is hidden.
echo  Keep this window open; closing it ends the session.
echo ============================================================
call claude remote-control

pause
endlocal
