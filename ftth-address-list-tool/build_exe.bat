@echo off
rem Builds the stand-alone Windows program (no Python needed on the computers that use it).
rem Run once on any Windows PC that has Python 3.11+ (https://www.python.org/downloads/).
rem Result: dist\FTTH_Address_List_Tool\ (copy this folder) and dist\FTTH_Address_List_Tool_v<version>_windows.zip
setlocal
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python 3.11 or newer is needed to BUILD the program ^(not to run it^). Install it from
  echo https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || (echo Python 3.11 or newer is required. & pause & exit /b 1)
echo Creating build environment ...
%PY% -m venv .build_venv || (echo Could not create the build environment. & pause & exit /b 1)
".build_venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".build_venv\Scripts\python.exe" -m pip install -r packaging\requirements-build.txt || (echo Package install failed. & pause & exit /b 1)
".build_venv\Scripts\python.exe" packaging\build.py || (echo BUILD FAILED - see the messages above. & pause & exit /b 1)
echo.
echo Done. Copy the folder dist\FTTH_Address_List_Tool to the other computers ^(or send the zip in dist\^).
explorer dist
pause
endlocal
