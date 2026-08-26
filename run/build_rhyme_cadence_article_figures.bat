@echo off
setlocal

set "ROOT=%~dp0.."
set "SCRIPT=%ROOT%\src\figures\build_rhyme_cadence_article_figures.py"
set "MAIN=%~1"
set "EXACT=%~2"
set "VERSE_NULL=%~3"
set "OUT=%~4"

if "%MAIN%"=="" set "MAIN=%ROOT%\results\core_rhyme\rhyme_cadence_distribution_robustness\main_strict"
if "%EXACT%"=="" set "EXACT=%ROOT%\results\core_rhyme\rhyme_cadence_distribution_robustness\control_strict_exclude_exact\ALL_block_distribution_statistics.csv"
if "%VERSE_NULL%"=="" set "VERSE_NULL=%ROOT%\results\core_rhyme\rhyme_cadence_additional_controls\verse_allocation_null\ALL_verse_coverage_null_statistics.csv"
if "%OUT%"=="" set "OUT=%ROOT%\figures\rhyme_cadence_distribution_robustness"

echo === BUILD RHYME-CADENCE ARTICLE FIGURES ===
echo SCRIPT=%SCRIPT%
echo MAIN=%MAIN%
echo EXACT=%EXACT%
echo VERSE_NULL=%VERSE_NULL%
echo OUT=%OUT%
echo.

if not exist "%SCRIPT%" (
    echo ERROR: figure builder not found: "%SCRIPT%"
    exit /b 1
)

if not exist "%MAIN%\ALL_verse_coverage.csv" (
    echo ERROR: MAIN output is incomplete: "%MAIN%"
    exit /b 1
)

if not exist "%EXACT%" (
    echo ERROR: exact-word control statistics not found: "%EXACT%"
    exit /b 1
)

if not exist "%VERSE_NULL%" (
    echo ERROR: verse-allocation null statistics not found: "%VERSE_NULL%"
    exit /b 1
)

py -3 "%SCRIPT%" ^
  --main-dir "%MAIN%" ^
  --exact-block-statistics "%EXACT%" ^
  --verse-null-statistics "%VERSE_NULL%" ^
  --out-dir "%OUT%" ^
  --dpi 600

if errorlevel 1 (
    echo FAILED.
    exit /b 1
)

echo.
echo DONE: manuscript figures were written to "%OUT%".
endlocal
