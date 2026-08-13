@echo off
setlocal

set "ROOT=%~dp0.."
pushd "%ROOT%" || exit /b 1

set BOOKS=--book genesis data\data_processed\torah\genesis_taamim_annotated.txt --book exodus data\data_processed\torah\exodus_taamim_annotated.txt --book leviticus data\data_processed\torah\leviticus_taamim_annotated.txt --book numbers data\data_processed\torah\numbers_taamim_annotated.txt --book deuteronomy data\data_processed\torah\deuteronomy_taamim_annotated.txt

echo === cyclic_shift ===
python src\analyses\core_taam\taam_temporal_structure.py ^
  --out_dir results\core_taam\taam_temporal_structure\control_cyclic_shift ^
  --run_label control_cyclic_shift --jobs 5 --interval_perm 500 --transition_perm 500 --seed 1 ^
  --null_model cyclic_shift --max_interval 40 --top_interval_ngram 50 --interval_ngram_ns 2,3,4,5,6 ^
  --top_shapes 50 --min_transition_count 5 --transition_top_k 50 ^
  --split_mode random --transition_accent_mode taam_events %BOOKS%
if errorlevel 1 goto :failed

echo === accent_words_chronological ===
python src\analyses\core_taam\taam_temporal_structure.py ^
  --out_dir results\core_taam\taam_temporal_structure\control_accent_words_chronological ^
  --run_label control_accent_words_chronological --jobs 5 --interval_perm 500 --transition_perm 500 --seed 1 ^
  --null_model global_interval_shuffle --max_interval 40 --top_interval_ngram 50 --interval_ngram_ns 2,3,4,5,6 ^
  --top_shapes 50 --min_transition_count 5 --transition_top_k 50 ^
  --split_mode chronological --transition_accent_mode accent_words %BOOKS%
if errorlevel 1 goto :failed

echo === descriptive_none ===
python src\analyses\core_taam\taam_temporal_structure.py ^
  --out_dir results\core_taam\taam_temporal_structure\control_descriptive_none ^
  --run_label control_descriptive_none --jobs 5 --interval_perm 0 --transition_perm 100 --seed 1 ^
  --null_model none --max_interval 80 --top_interval_ngram 50 --interval_ngram_ns 2,3,4,5,6 ^
  --top_shapes 50 --min_transition_count 20 --transition_top_k 50 ^
  --split_mode random --transition_accent_mode taam_events %BOOKS%
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
