@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "SCRIPT=src\analyses\core_rhyme\rhyme_burst_architecture.py"
set "OUT=results\core_rhyme\rhyme_burst_architecture\main_strict"

echo === RHYME BURST ARCHITECTURE: MAIN STRICT ===
python "%SCRIPT%" ^
  --source-dir "%SOURCE%" ^
  --out-dir "%OUT%" ^
  --run-label main_strict ^
  --window 20 ^
  --enrichment-permutations 500 ^
  --clustering-permutations 500 ^
  --boundary-permutations 1000 ^
  --activity-threshold 1 ^
  --match-filter ALL ^
  --equivalence-profile STRICT ^
  --seed 20260728 ^
  --jobs 5

if errorlevel 1 exit /b 1
echo MAIN COMPLETED.
endlocal
