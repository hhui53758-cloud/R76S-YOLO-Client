@echo off
rem Validated with a physical R76S on 2026-10-08.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0network_to_r76s.ps1"
if errorlevel 1 pause
