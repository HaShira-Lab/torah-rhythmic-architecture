@echo off
setlocal
REM Larger descriptive output and lower transition threshold. Exploratory, not article-facing.

set "ROOT=%~dp0.."
pushd "%ROOT%" || exit /b 1

python src\analyses\core_taam\taam_temporal_structure.py ^
  --out_dir results\core_taam\taam_temporal_structure\explore_large_output ^
  --run_label explore_large_output ^
  --jobs 5 ^
  --interval_perm 250 ^
  --transition_perm 250 ^
  --seed 1 ^
  --null_model global_interval_shuffle ^
  --max_interval 80 ^
  --top_interval_ngram 500 ^
  --interval_ngram_ns 2,3,4,5,6,7 ^
  --top_shapes 500 ^
  --min_transition_count 3 ^
  --transition_top_k 200 ^
  --split_mode random ^
  --transition_accent_mode taam_events ^
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
set "RC=%ERRORLEVEL%"
echo.
echo FAILED with exit code %RC%
popd
pause
exit /b %RC%
