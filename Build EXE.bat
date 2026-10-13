@echo off
rem Builds a single EQLAssistant.exe in this folder. Needs Python installed once.
cd /d "%~dp0"

rem The app window (pywebview) supports Python 3.10-3.13 best, so prefer those.
set PY=
for %%V in (3.13 3.12 3.11 3.10) do (
  if not defined PY ( py -%%V -c "pass" >nul 2>nul && set PY=py -%%V )
)
if not defined PY ( where py >nul 2>nul && set PY=py -3 )
if not defined PY ( where python >nul 2>nul && set PY=python )
if not defined PY (
  echo Python was not found. Install Python 3.13 from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup, then run this again.
  pause
  exit /b 1
)
echo Using: %PY%
%PY% --version

echo.
echo Installing build tools...
%PY% -m pip install --upgrade --quiet pyinstaller || goto :fail
set WEBVIEW=1
%PY% -m pip install --upgrade --quiet pywebview || set WEBVIEW=0
%PY% -m pip install --upgrade --quiet pillow || echo NOTE: Pillow could not be installed - crawl timer pictures for the leaderboard will be skipped.
if "%WEBVIEW%"=="0" (
  echo.
  echo NOTE: pywebview could not be installed for this Python version.
  echo The .exe will still work, but opens in your web browser instead of its own window.
  echo Installing Python 3.13 and running this again fixes that.
  echo.
)

echo Building EQLAssistant.exe - this takes a minute or two...
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name EQLAssistant ^
  --icon assets\icon.ico ^
  --add-data "web;web" ^
  --add-data "assets\icon.ico;assets" ^
  --hidden-import overlay_window ^
  --hidden-import PIL.ImageGrab --hidden-import PIL.ImageDraw --hidden-import PIL.ImageFont ^
  --collect-submodules eqlc ^
  main.py || goto :fail

copy /y "dist\EQLAssistant.exe" "EQLAssistant.exe" >nul
rmdir /s /q build >nul 2>nul
del /q EQLAssistant.spec >nul 2>nul
echo.
echo Done! EQLAssistant.exe is in this folder. You can move it anywhere.
pause
exit /b 0

:fail
echo.
echo Build failed - copy the messages above and send them over.
pause
exit /b 1
