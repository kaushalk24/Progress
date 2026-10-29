@echo off
rem Command-line use, e.g.:
rem   run_cli.bat run --reports "C:\Region\Splice Reports" --out "C:\Region\Out" --prefix "123456_Example City ST"
setlocal
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -m ftth_addrlist %*
endlocal
