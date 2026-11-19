@echo off
rem Double-click: updates the arcade on every Pi listed in pis.txt.
rem Extra options (from a terminal): --only NAME, --restart, --dry-run, --setup-keys
cd /d "%~dp0"
py -3 update_pis.py %*
if errorlevel 9009 python update_pis.py %*
echo.
pause
