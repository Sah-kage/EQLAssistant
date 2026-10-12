@echo off
cd /d "%~dp0"
rem Run this after "Start EQL Assistant.bat" is already running
rem (or just use the "Open in-game overlay window" button on the dashboard).
where pyw >nul 2>nul && (start "" pyw -3 main.py --overlay-only) || (start "" pythonw main.py --overlay-only)
