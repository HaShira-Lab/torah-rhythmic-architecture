@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "SCRIPT=src\analyses\core_rhyme\burst_profile_inside_taam_hierarchy.py"

REM Sensitivity only. STRICT remains the scientific baseline.
for %%P in (STRICT VF DT PB QK H_KH TS_S VOICING TRADITION VOICING_TRADITION EXPANDED_ALL) do (
  echo.
  echo === EQUIVALENCE PROFILE: %%P ===
  python "%SCRIPT%" ^
    --source-dir "%SOURCE%" ^
    --out-dir "results\core_rhyme\burst_profile_inside_taam_hierarchy\explore_equivalence_%%P" ^
    --run-label "explore_equivalence_%%P" ^
    --window 20 ^
    --circular-permutations 250 ^
    --within-permutations 250 ^
    --activity-threshold 1 ^
    --match-filter ALL ^
    --equivalence-profile %%P ^
    --bins 5 ^
    --coordinate-mode normalized ^
    --aggregation segment ^
    --value-mode raw ^
    --min-segment-length 3 ^
    --max-segment-length 0 ^
    --seed 20260728 ^
    --jobs 5
  if errorlevel 1 exit /b 1
)

echo ALL EQUIVALENCE-PROFILE EXPLORE RUNS COMPLETED.
endlocal

