@echo off
setlocal
pushd "%~dp0.."
if errorlevel 1 goto :error

python src\analyses\core_taam\taam_boundary_reconstruction.py ^
  --out_dir results\core_taam\taam_boundary_reconstruction\main ^
  --run_label main ^
  --jobs 5 ^
  --feature_sets default ^
  --evaluation_mode cross_validation ^
  --folds 5 ^
  --split_mode major_unit ^
  --random_perm 1000 ^
  --paired_perm 10000 ^
  --pos_cap 10 ^
  --len_cap 30 ^
  --top_weights 80 ^
  --alpha 1.0 ^
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
