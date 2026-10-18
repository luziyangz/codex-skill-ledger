@echo off
powershell.exe -NoProfile -File "%~dp0scripts\manage.ps1" -Action Open
if errorlevel 1 pause
