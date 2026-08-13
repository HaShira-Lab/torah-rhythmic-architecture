@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "SCRIPT=src\analyses\core_rhyme\rhyme_cadence_distribution_robustness.py"

REM label window threshold filter block_size extra
call :run control_strict_exclude_exact 20 1 ALL 1000 --exclude-exact
if errorlevel 1 exit /b 1
call :run control_strict_full_only 20 1 FULL 1000
if errorlevel 1 exit /b 1
call :run control_strict_full_exclude_exact 20 1 FULL 1000 --exclude-exact
if errorlevel 1 exit /b 1
call :run control_strict_bridge_only 20 1 BRIDGE 1000
if errorlevel 1 exit /b 1
call :run control_strict_threshold2 20 2 ALL 1000
if errorlevel 1 exit /b 1
call :run control_strict_L10 10 1 ALL 1000
if errorlevel 1 exit /b 1
call :run control_strict_L50 50 1 ALL 1000
if errorlevel 1 exit /b 1
call :run control_strict_block500 20 1 ALL 500
if errorlevel 1 exit /b 1
call :run control_strict_block2000 20 1 ALL 2000
if errorlevel 1 exit /b 1

echo ALL STRICT CONTROLS COMPLETED.
endlocal
exit /b 0

:run
set "LABEL=%~1"
set "WINDOW=%~2"
set "THRESHOLD=%~3"
set "FILTER=%~4"
set "BLOCK=%~5"
set "EXTRA=%~6"
echo.
echo === %LABEL% ===
python "%SCRIPT%" ^
  --source-dir "%SOURCE%" ^
  --out-dir "results\core_rhyme\rhyme_cadence_distribution_robustness\%LABEL%" ^
  --run-label "%LABEL%" ^
  --window %WINDOW% ^
  --activity-threshold %THRESHOLD% ^
  --match-filter %FILTER% ^
  --equivalence-profile STRICT ^
  --block-size %BLOCK% ^
  --minimum-block-fraction 0.5 ^
  --minimum-burst-ends-per-block 5 ^
  --boundary-permutations 500 ^
  --seed 20260728 ^
  --jobs 5 %EXTRA%
exit /b %errorlevel%
