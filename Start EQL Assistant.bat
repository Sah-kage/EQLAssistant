@echo off
rem Runs EQL Assistant from source (no build needed).
cd /d "%~dp0"
set PY=python
set PYW=pythonw
where py >nul 2>nul && (set PY=py -3& set PYW=pyw -3)
%PY% -c "import webview" >nul 2>nul || %PY% -m pip install --quiet pywebview
start "" %PYW% main.py %*
