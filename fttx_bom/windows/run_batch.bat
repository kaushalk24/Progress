@echo off
REM Usage: run_batch.bat "C:\Jobs" "C:\Jobs\out" ["C:\Templates\BOM_template.xlsx"]
REM Every sub-folder of the jobs folder is one network (drawing + address list + splice reports, zips are fine).
cd /d "%~dp0\.."
if "%~2"=="" (echo Usage: run_batch.bat JOBS_FOLDER OUTPUT_FOLDER [TEMPLATE] & pause & exit /b 1)
if "%~3"=="" (python -m fttx_bom batch "%~1" --out "%~2") else (python -m fttx_bom batch "%~1" --out "%~2" --template "%~3")
pause
