@echo off
setlocal

set PYTHON_EXE=C:\Users\omert\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
set FIREBASE_SERVICE_ACCOUNT=C:\Users\omert\Downloads\moran-cce72-firebase-adminsdk-fbsvc-55d361cb9b.json
cd /d "%~dp0"

if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" daily_scan.py
) else (
  python daily_scan.py
)

endlocal
