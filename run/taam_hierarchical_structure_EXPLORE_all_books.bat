@echo off
setlocal
REM Exploratory long-tail output for size sequences. Descriptive only.

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" || exit /b 1

python "src\analyses\core_taam\taam_hierarchical_structure.py" ^
  --out_dir results\core_taam\taam_hierarchical_structure\explore_ngram500 ^
  --run_label explore_ngram500 ^
  --jobs 5 ^
  --max_words 80 ^
  --max_pulses 160 ^
  --max_accents 50 ^
  --top_ngram 500 ^
  --ngram_ns 2,3,4,5,6 ^
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
