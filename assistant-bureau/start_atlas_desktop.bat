@echo off
setlocal

set ROOT=%~dp0

if not exist "%ROOT%..\.venv\Scripts\python.exe" (
  echo [ERROR] Python venv missing at ..\.venv
  exit /b 1
)

echo [1/2] Starting Atlas API...
start "Atlas API" "%ROOT%..\.venv\Scripts\python.exe" "%ROOT%main.py"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Atlas Desktop...
"%ROOT%..\.venv\Scripts\python.exe" "%ROOT%desktop\atlas_desktop.py"

endlocal
