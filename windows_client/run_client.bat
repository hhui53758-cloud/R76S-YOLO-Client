@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows_client\install_windows_client.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" windows_client\app.py
if errorlevel 1 pause
