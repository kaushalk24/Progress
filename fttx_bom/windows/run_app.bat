@echo off
REM Starts the FTTx BOM Tool in your browser (runs only on this computer).
cd /d "%~dp0\.."
python -m fttx_bom app
pause
