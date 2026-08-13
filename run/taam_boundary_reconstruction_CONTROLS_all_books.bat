@echo off
setlocal
pushd "%~dp0.."
if errorlevel 1 goto :error

echo === random_words ===
python src\analyses\core_taam\taam_boundary_reconstruction.py ^
  --out_dir results\core_taam\taam_boundary_reconstruction\control_random_words ^
  --run_label control_random_words --jobs 5 --feature_sets default ^
  --evaluation_mode cross_validation --folds 5 --split_mode random_words ^
  --random_perm 500 --paired_perm 5000 ^
  --book genesis data\data_processed\torah\genesis_taamim_annotated.txt ^
  --book exodus data\data_processed\torah\exodus_taamim_annotated.txt ^
  --book leviticus data\data_processed\torah\leviticus_taamim_annotated.txt ^
  --book numbers data\data_processed\torah\numbers_taamim_annotated.txt ^
  --book deuteronomy data\data_processed\torah\deuteronomy_taamim_annotated.txt
if errorlevel 1 goto :error

echo === include_edges ===
python src\analyses\core_taam\taam_boundary_reconstruction.py ^
  --out_dir results\core_taam\taam_boundary_reconstruction\control_include_edges ^
  --run_label control_include_edges --jobs 5 --feature_sets default ^
  --evaluation_mode cross_validation --folds 5 --split_mode major_unit ^
  --random_perm 500 --paired_perm 5000 --include_edges ^
  --book genesis data\data_processed\torah\genesis_taamim_annotated.txt ^
  --book exodus data\data_processed\torah\exodus_taamim_annotated.txt ^
  --book leviticus data\data_processed\torah\leviticus_taamim_annotated.txt ^
  --book numbers data\data_processed\torah\numbers_taamim_annotated.txt ^
  --book deuteronomy data\data_processed\torah\deuteronomy_taamim_annotated.txt
if errorlevel 1 goto :error

echo === wider_caps ===
python src\analyses\core_taam\taam_boundary_reconstruction.py ^
  --out_dir results\core_taam\taam_boundary_reconstruction\control_wider_caps ^
  --run_label control_wider_caps --jobs 5 --feature_sets default ^
  --evaluation_mode cross_validation --folds 5 --split_mode major_unit ^
  --random_perm 500 --paired_perm 5000 --pos_cap 16 --len_cap 40 ^
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
