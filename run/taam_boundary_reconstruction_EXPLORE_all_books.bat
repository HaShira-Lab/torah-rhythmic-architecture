@echo off
setlocal
pushd "%~dp0.."
if errorlevel 1 goto :error

python src\analyses\core_taam\taam_boundary_reconstruction.py ^
  --out_dir results\core_taam\taam_boundary_reconstruction\explore_holdout30 ^
  --run_label explore_holdout30 --jobs 5 --feature_sets default ^
  --evaluation_mode holdout --split_mode major_unit --test_frac 0.30 ^
  --random_perm 500 --paired_perm 5000 --top_weights 200 ^
  --book genesis data\data_processed\torah\genesis_taamim_annotated.txt ^
  --book exodus data\data_processed\torah\exodus_taamim_annotated.txt ^
  --book leviticus data\data_processed\torah\leviticus_taamim_annotated.txt ^
  --book numbers data\data_processed\torah\numbers_taamim_annotated.txt ^
  --book deuteronomy data\data_processed\torah\deuteronomy_taamim_annotated.txt
if errorlevel 1 goto :error

popd
endlocal
exit /b 0

:error
set "TAAM_EXIT=%errorlevel%"
popd
endlocal & exit /b %TAAM_EXIT%
