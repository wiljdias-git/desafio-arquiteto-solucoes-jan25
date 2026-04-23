@echo off
setlocal

set "ROOT_DIR=%~dp0.."

if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
  "%ROOT_DIR%\.venv\Scripts\python.exe" "%ROOT_DIR%\scripts\demo_real.py" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python "%ROOT_DIR%\scripts\demo_real.py" %*
  exit /b %ERRORLEVEL%
)

py -3 "%ROOT_DIR%\scripts\demo_real.py" %*
exit /b %ERRORLEVEL%
