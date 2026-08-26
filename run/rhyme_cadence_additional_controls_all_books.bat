@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "MAIN=results\core_rhyme\rhyme_cadence_distribution_robustness\main_strict"
set "SCRIPT=src\analyses\core_rhyme\rhyme_cadence_additional_controls.py"
set "OUT=results\core_rhyme\rhyme_cadence_additional_controls"

echo === RHYME-CADENCE ADDITIONAL CONTROLS v1.0.0 ===
echo.

echo [1/3] Boundary control without paseq in the operational minor set
py -3 "%SCRIPT%" boundary_no_paseq ^
  --source-dir "%SOURCE%" ^
  --out-dir "%OUT%" ^
  --boundary-permutations 1000 ^
  --seed 20260728
if errorlevel 1 goto :failed

echo.
echo [2/3] Control excluding links that depend on final-vowel extension
py -3 "%SCRIPT%" exclude_extended_left ^
  --source-dir "%SOURCE%" ^
  --out-dir "%OUT%" ^
  --enrichment-permutations 500 ^
  --clustering-permutations 500 ^
  --boundary-permutations 1000 ^
  --seed 20260728
if errorlevel 1 goto :failed

echo.
echo [3/3] Conditional canonical-verse allocation null
py -3 "%SCRIPT%" verse_allocation_null ^
  --main-dir "%MAIN%" ^
  --out-dir "%OUT%" ^
  --verse-permutations 5000 ^
  --seed 20260728
if errorlevel 1 goto :failed

echo.
echo DONE: all additional controls completed.
echo Output directory: "%OUT%"
endlocal
exit /b 0

:failed
echo.
echo FAILED with errorlevel %errorlevel%.
endlocal
exit /b 1
