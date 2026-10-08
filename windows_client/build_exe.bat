@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows_client\install_windows_client.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\build_windows.py
if errorlevel 1 goto failed
echo Build completed. See release directory.
pause
exit /b 0
:failed
echo Build failed.
pause
exit /b 1
