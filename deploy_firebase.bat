@echo off
REM One-click Firebase Hosting deploy for the Moran job dashboard.
REM Double-click this file. A browser opens for Google login the first time,
REM then the static dashboard is deployed to https://moran-cce72.web.app

setlocal
set "NODEDIR=C:\Users\omert\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.16.0-win-x64"
set "PATH=%NODEDIR%;%PATH%"
cd /d "%~dp0"

echo ============================================================
echo  Step 1/2: Using local Firebase service account.
echo ============================================================
set "GOOGLE_APPLICATION_CREDENTIALS=C:\Users\omert\Downloads\moran-cce72-firebase-adminsdk-fbsvc-55d361cb9b.json"

echo.
echo ============================================================
echo  Step 2/2: Deploying dashboard + Realtime Database rules...
echo ============================================================
call firebase.cmd deploy --only hosting,database --project moran-cce72

echo.
echo Done. Your dashboard: https://moran-cce72.web.app
pause
endlocal
