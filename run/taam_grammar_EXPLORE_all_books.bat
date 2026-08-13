@echo off
setlocal
REM run\taam_grammar_EXPLORE_all_books.bat
REM Exploratory extension: longer formulas and lower edge thresholds.
REM Candidate-level p-values are exploratory screening statistics; unreliable Z values are suppressed.

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" || exit /b 1

python "src\analyses\core_taam\taam_grammar.py" ^
  --out_dir results\core_taam\taam_grammar\explore_k3_7_edges20 ^
  --run_label explore_k3_7_edges20 ^
  --entropy_k 2,3,4,5,6,7 ^
  --formula_k 3,4,5,6,7 ^
  --transition_perm 250 ^
  --formula_perm 200 ^
  --seed 1 ^
  --jobs 5 ^
  --min_transition_count 20 ^
  --min_formula_count 20 ^
  --formula_candidates 500 ^
  --top_k 100 ^
  --top_n 15 ^
  --min_edge_count 20 ^
  --core_min_edge_count 20 ^
  --core_min_prob 0.10 ^
  --book genesis data\data_processed\torah\genesis_taamim_annotated.txt ^
  --book exodus data\data_processed\torah\exodus_taamim_annotated.txt ^
  --book leviticus data\data_processed\torah\leviticus_taamim_annotated.txt ^
  --book numbers data\data_processed\torah\numbers_taamim_annotated.txt ^
  --book deuteronomy data\data_processed\torah\deuteronomy_taamim_annotated.txt

if errorlevel 1 goto :failed
echo.
echo DONE
popd
pause
exit /b 0

:failed
echo.
echo FAILED
popd
pause
exit /b 1
