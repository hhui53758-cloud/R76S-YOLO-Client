@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r windows_client\requirements.txt
if errorlevel 1 goto failed
echo Installation completed. Run windows_client\run_client.bat next.
pause
exit /b 0
:failed
echo Installation failed. Install Python 3.11 or 3.12 with the Python launcher first.
pause
exit /b 1
