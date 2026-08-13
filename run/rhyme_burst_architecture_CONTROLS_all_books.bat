@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "SCRIPT=src\analyses\core_rhyme\rhyme_burst_architecture.py"

REM label window threshold filter extra
call :run control_strict_exclude_exact 20 1 ALL --exclude-exact
if errorlevel 1 exit /b 1
call :run control_strict_full_only 20 1 FULL
if errorlevel 1 exit /b 1
call :run control_strict_full_exclude_exact 20 1 FULL --exclude-exact
if errorlevel 1 exit /b 1
call :run control_strict_bridge_only 20 1 BRIDGE
if errorlevel 1 exit /b 1
call :run control_strict_threshold2 20 2 ALL
if errorlevel 1 exit /b 1
call :run control_strict_L10 10 1 ALL
if errorlevel 1 exit /b 1
call :run control_strict_L50 50 1 ALL
if errorlevel 1 exit /b 1

echo ALL STRICT CONTROLS COMPLETED.
endlocal
exit /b 0

:run
set "LABEL=%~1"
set "WINDOW=%~2"
set "THRESHOLD=%~3"
set "FILTER=%~4"
set "EXTRA=%~5"
echo.
echo === %LABEL% ===
python "%SCRIPT%" ^
  --source-dir "%SOURCE%" ^
  --out-dir "results\core_rhyme\rhyme_burst_architecture\%LABEL%" ^
  --run-label "%LABEL%" ^
  --window %WINDOW% ^
  --enrichment-permutations 250 ^
  --clustering-permutations 250 ^
  --boundary-permutations 500 ^
  --activity-threshold %THRESHOLD% ^
  --match-filter %FILTER% ^
  --equivalence-profile STRICT ^
  --seed 20260728 ^
  --jobs 5 %EXTRA%
exit /b %errorlevel%
