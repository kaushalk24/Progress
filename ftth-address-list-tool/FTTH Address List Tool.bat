@echo off
rem Double-click to open the FTTH address-list generator window.
setlocal
cd /d "%~dp0"
set "PY="
set "PYW="
where py >nul 2>nul && (set "PY=py -3" & set "PYW=pyw -3")
if not defined PY (where python >nul 2>nul && (set "PY=python" & set "PYW=pythonw"))
if not defined PY (
  echo Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || (
  echo Python 3.11 or newer is required.
  pause
  exit /b 1
)
%PY% -c "import openpyxl" 2>nul || (
  echo Installing required packages ...
  %PY% -m pip install --user -r requirements.txt || (echo Could not install requirements. & pause & exit /b 1)
)
start "" %PYW% -m ftth_addrlist.gui
endlocal
