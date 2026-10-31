@echo off
rem Runs start.ps1 without changing the machine's PowerShell execution policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
