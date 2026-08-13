@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "SCRIPT=src\analyses\core_rhyme\burst_profile_inside_taam_hierarchy.py"
set "OUT=results\core_rhyme\burst_profile_inside_taam_hierarchy\main_strict"

echo === BURST PROFILE INSIDE TAAM HIERARCHY: MAIN STRICT ===
python "%SCRIPT%" ^
  --source-dir "%SOURCE%" ^
  --out-dir "%OUT%" ^
  --run-label main_strict ^
  --window 20 ^
  --circular-permutations 1000 ^
  --within-permutations 1000 ^
  --activity-threshold 1 ^
  --match-filter ALL ^
  --equivalence-profile STRICT ^
  --bins 5 ^
  --coordinate-mode normalized ^
  --aggregation segment ^
  --value-mode raw ^
  --min-segment-length 3 ^
  --max-segment-length 0 ^
  --seed 20260728 ^
  --jobs 5

if errorlevel 1 exit /b 1
echo MAIN COMPLETED.
endlocal

