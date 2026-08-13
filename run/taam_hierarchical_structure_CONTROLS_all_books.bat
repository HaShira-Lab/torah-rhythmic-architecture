@echo off
setlocal EnableDelayedExpansion
REM Output-stability controls. These change only reporting ranges/list length,
REM not segmentation, level definitions, or underlying observations.

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" || exit /b 1

for %%R in (large_ranges top200) do (
  if "%%R"=="large_ranges" (
    set MAXW=80
    set MAXP=160
    set MAXA=50
    set TOPN=50
  )
  if "%%R"=="top200" (
    set MAXW=40
    set MAXP=80
    set MAXA=25
    set TOPN=200
  )

  echo === %%R ===
  python "src\analyses\core_taam\taam_hierarchical_structure.py" ^
    --out_dir results\core_taam\taam_hierarchical_structure\control_%%R ^
    --run_label control_%%R ^
    --jobs 5 ^
    --max_words !MAXW! ^
    --max_pulses !MAXP! ^
    --max_accents !MAXA! ^
    --top_ngram !TOPN! ^
    --ngram_ns 2,3,4,5,6 ^
    --book genesis data\data_processed\torah\genesis_taamim_annotated.txt ^
    --book exodus data\data_processed\torah\exodus_taamim_annotated.txt ^
    --book leviticus data\data_processed\torah\leviticus_taamim_annotated.txt ^
    --book numbers data\data_processed\torah\numbers_taamim_annotated.txt ^
    --book deuteronomy data\data_processed\torah\deuteronomy_taamim_annotated.txt
  if errorlevel 1 goto :failed
)

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
