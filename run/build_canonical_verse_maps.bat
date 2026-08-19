@echo off
setlocal

echo === BUILD VERIFIED CANONICAL VERSE MAPS ===

set "REPO_ROOT=%~dp0.."
set "SCRIPT=%REPO_ROOT%\src\tools\build_canonical_verse_maps.py"
set "PREPROCESSOR=%REPO_ROOT%\src\preprocessing\preprocessing_phonetic_taamim_annotated.py"
set "PROCESSED_DIR=%REPO_ROOT%\data\data_processed\torah"

if not exist "%SCRIPT%" (
    echo ERROR: generator not found: "%SCRIPT%"
    goto :failed
)

if not exist "%PREPROCESSOR%" (
    echo ERROR: preprocessor not found: "%PREPROCESSOR%"
    goto :failed
)

if not exist "%PROCESSED_DIR%\genesis_taamim_annotated.txt" (
    echo ERROR: processed Torah files not found in: "%PROCESSED_DIR%"
    goto :failed
)

py -3 "%SCRIPT%" ^
    --processed-dir "%PROCESSED_DIR%" ^
    --preprocessor "%PREPROCESSOR%"

if errorlevel 1 goto :failed

for %%B in (genesis exodus leviticus numbers deuteronomy) do (
    if not exist "%PROCESSED_DIR%\%%B_taamim_annotated.txt.verse_map.json" (
        echo ERROR: expected map was not created for %%B
        goto :failed
    )
)

echo.
echo DONE: all five canonical verse maps were generated and verified.
echo Output directory: "%PROCESSED_DIR%"
pause
exit /b 0

:failed
echo.
echo FAILED: canonical verse maps were not completed.
pause
exit /b 1
