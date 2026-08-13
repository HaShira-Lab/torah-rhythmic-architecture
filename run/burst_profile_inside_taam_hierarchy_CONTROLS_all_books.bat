@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "SCRIPT=src\analyses\core_rhyme\burst_profile_inside_taam_hierarchy.py"

REM label window threshold filter aggregation value minlen coordinate bins extra
call :run control_strict_exclude_exact 20 1 ALL segment raw 3 normalized 5 --exclude-exact
if errorlevel 1 exit /b 1
call :run control_strict_full_only 20 1 FULL segment raw 3 normalized 5
if errorlevel 1 exit /b 1
call :run control_strict_full_exclude_exact 20 1 FULL segment raw 3 normalized 5 --exclude-exact
if errorlevel 1 exit /b 1
call :run control_strict_bridge_only 20 1 BRIDGE segment raw 3 normalized 5
if errorlevel 1 exit /b 1
call :run control_strict_threshold2 20 2 ALL segment raw 3 normalized 5
if errorlevel 1 exit /b 1
call :run control_strict_L10 10 1 ALL segment raw 3 normalized 5
if errorlevel 1 exit /b 1
call :run control_strict_L50 50 1 ALL segment raw 3 normalized 5
if errorlevel 1 exit /b 1
call :run control_strict_exclude_cadence_word 20 1 ALL segment raw 3 normalized 5 --exclude-cadence-word
if errorlevel 1 exit /b 1
call :run control_strict_token_pooled 20 1 ALL token raw 3 normalized 5
if errorlevel 1 exit /b 1
call :run control_strict_minlen5 20 1 ALL segment raw 5 normalized 5
if errorlevel 1 exit /b 1
call :run control_strict_minlen8 20 1 ALL segment raw 8 normalized 5
if errorlevel 1 exit /b 1
call :run control_strict_distance7 20 1 ALL segment raw 3 distance 8
if errorlevel 1 exit /b 1
call :run control_strict_share_normalized 20 1 ALL segment share 3 normalized 5
if errorlevel 1 exit /b 1

echo ALL STRICT PROFILE CONTROLS COMPLETED.
endlocal
exit /b 0

:run
set "LABEL=%~1"
set "WINDOW=%~2"
set "THRESHOLD=%~3"
set "FILTER=%~4"
set "AGGREGATION=%~5"
set "VALUE_MODE=%~6"
set "MINLEN=%~7"
set "COORDINATE=%~8"
set "BINS=%~9"
shift
shift
shift
shift
shift
shift
shift
shift
shift
set "EXTRA=%~1"

echo.
echo === %LABEL% ===
python "%SCRIPT%" ^
  --source-dir "%SOURCE%" ^
  --out-dir "results\core_rhyme\burst_profile_inside_taam_hierarchy\%LABEL%" ^
  --run-label "%LABEL%" ^
  --window %WINDOW% ^
  --circular-permutations 500 ^
  --within-permutations 500 ^
  --activity-threshold %THRESHOLD% ^
  --match-filter %FILTER% ^
  --equivalence-profile STRICT ^
  --bins %BINS% ^
  --coordinate-mode %COORDINATE% ^
  --max-distance 7 ^
  --aggregation %AGGREGATION% ^
  --value-mode %VALUE_MODE% ^
  --min-segment-length %MINLEN% ^
  --max-segment-length 0 ^
  --seed 20260728 ^
  --jobs 5 %EXTRA%
exit /b %errorlevel%

