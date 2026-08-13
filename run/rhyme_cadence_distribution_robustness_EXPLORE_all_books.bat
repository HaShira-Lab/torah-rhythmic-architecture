@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "SCRIPT=src\analyses\core_rhyme\rhyme_cadence_distribution_robustness.py"

REM Sensitivity only. STRICT remains the scientific baseline.
for %%P in (STRICT VF DT PB QK H_KH TS_S VOICING TRADITION VOICING_TRADITION EXPANDED_ALL) do (
  echo.
  echo === EQUIVALENCE PROFILE: %%P ===
  python "%SCRIPT%" ^
    --source-dir "%SOURCE%" ^
    --out-dir "results\core_rhyme\rhyme_cadence_distribution_robustness\explore_equivalence_%%P" ^
    --run-label "explore_equivalence_%%P" ^
    --window 20 ^
    --activity-threshold 1 ^
    --match-filter ALL ^
    --equivalence-profile %%P ^
    --block-size 1000 ^
    --minimum-block-fraction 0.5 ^
    --minimum-burst-ends-per-block 5 ^
    --boundary-permutations 500 ^
    --seed 20260728 ^
    --jobs 5
  if errorlevel 1 exit /b 1
)

echo ALL EQUIVALENCE-PROFILE EXPLORE RUNS COMPLETED.
endlocal
