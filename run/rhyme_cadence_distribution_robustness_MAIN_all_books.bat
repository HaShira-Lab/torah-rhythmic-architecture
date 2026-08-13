@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "SCRIPT=src\analyses\core_rhyme\rhyme_cadence_distribution_robustness.py"
set "OUT=results\core_rhyme\rhyme_cadence_distribution_robustness\main_strict"

echo === RHYME-CADENCE DISTRIBUTION AND ROBUSTNESS: MAIN STRICT ===
python "%SCRIPT%" ^
  --source-dir "%SOURCE%" ^
  --out-dir "%OUT%" ^
  --run-label main_strict ^
  --window 20 ^
  --activity-threshold 1 ^
  --match-filter ALL ^
  --equivalence-profile STRICT ^
  --block-size 1000 ^
  --minimum-block-fraction 0.5 ^
  --minimum-burst-ends-per-block 5 ^
  --boundary-permutations 1000 ^
  --seed 20260728 ^
  --jobs 5

if errorlevel 1 exit /b 1
echo MAIN COMPLETED.
endlocal
