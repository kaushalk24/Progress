@echo off
REM One-time setup of the FTTx BOM Tool on Windows.
REM Needs: Python 3.11+ (python.org, tick "Add to PATH") and Node.js 20+ (nodejs.org).
REM Optional: LibreOffice (libreoffice.org) so the tool can recalculate and check the BOM formulas.
cd /d "%~dp0\.."
where python >nul 2>nul || (echo Python not found - install it from python.org and tick "Add python.exe to PATH". & pause & exit /b 1)
where node >nul 2>nul || (echo Node.js not found - install the LTS version from nodejs.org. & pause & exit /b 1)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || (echo pip install failed & pause & exit /b 1)
pushd tools
call npm install --ignore-scripts || (echo npm install failed & popd & pause & exit /b 1)
popd
where soffice >nul 2>nul || echo NOTE: LibreOffice not on PATH - BOMs are still produced, but formulas are not recalculated/verified.
echo.
echo Setup complete. Start the tool with windows\run_app.bat
pause
