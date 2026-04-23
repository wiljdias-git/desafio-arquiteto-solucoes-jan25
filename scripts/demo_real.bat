@echo off
setlocal

set "ROOT_DIR=%~dp0.."

if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
  "%ROOT_DIR%\.venv\Scripts\python.exe" "%ROOT_DIR%\scripts\demo_real.py" %*
  exit /b %ERRORLEVEL%
)

powershell -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\bootstrap_windows.ps1"
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
  "%ROOT_DIR%\.venv\Scripts\python.exe" "%ROOT_DIR%\scripts\demo_real.py" %*
  exit /b %ERRORLEVEL%
)

echo [FAIL] Nao foi possivel localizar .venv\Scripts\python.exe apos o bootstrap.
exit /b 1
