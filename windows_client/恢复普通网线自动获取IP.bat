@echo off
rem Safe DHCP and captive-portal workflow validated on 2026-10-08.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0network_to_dhcp.ps1"
if errorlevel 1 pause
