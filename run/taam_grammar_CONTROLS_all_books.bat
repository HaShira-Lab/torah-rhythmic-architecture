@echo off
setlocal
REM run\taam_grammar_CONTROLS_all_books.bat
REM Two prespecified controls with the same parameters as MAIN.

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" || exit /b 1

REM CONTROL 1: remove external {...} events.
python "src\analyses\core_taam\taam_grammar.py" ^
  --out_dir results\core_taam\taam_grammar\control_exclude_external ^
  --run_label control_exclude_external ^
  --entropy_k 2,3,4,5,6 ^
  --formula_k 3,4,5,6 ^
  --transition_perm 500 ^
  --formula_perm 200 ^
  --seed 1 ^
  --jobs 5 ^
  --min_transition_count 20 ^
  --min_formula_count 20 ^
  --formula_candidates 250 ^
  --top_k 50 ^
  --top_n 10 ^
  --min_edge_count 5 ^
  --core_min_edge_count 100 ^
  --core_min_prob 0.15 ^
  --exclude_external ^
  --book genesis data\data_processed\torah\genesis_taamim_annotated.txt ^
  --book exodus data\data_processed\torah\exodus_taamim_annotated.txt ^
  --book leviticus data\data_processed\torah\leviticus_taamim_annotated.txt ^
  --book numbers data\data_processed\torah\numbers_taamim_annotated.txt ^
  --book deuteronomy data\data_processed\torah\deuteronomy_taamim_annotated.txt
if errorlevel 1 goto :failed

REM CONTROL 2: remove meteg.
python "src\analyses\core_taam\taam_grammar.py" ^
  --out_dir results\core_taam\taam_grammar\control_exclude_meteg ^
  --run_label control_exclude_meteg ^
  --entropy_k 2,3,4,5,6 ^
  --formula_k 3,4,5,6 ^
  --transition_perm 500 ^
  --formula_perm 200 ^
  --seed 1 ^
  --jobs 5 ^
  --min_transition_count 20 ^
  --min_formula_count 20 ^
  --formula_candidates 250 ^
  --top_k 50 ^
  --top_n 10 ^
  --min_edge_count 5 ^
  --core_min_edge_count 100 ^
  --core_min_prob 0.15 ^
  --exclude_taamim meteg ^
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
