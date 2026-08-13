@echo off
setlocal

echo === PREPROCESSING: PHONETIC TAAM ANNOTATION ===

set "REPO_ROOT=%~dp0.."
set "SCRIPT=%REPO_ROOT%\src\preprocessing\preprocessing_phonetic_taamim_annotated.py"
set "TORAH_IN=%REPO_ROOT%\data\data_raw\torah"
set "TORAH_OUT=%REPO_ROOT%\data\data_processed\torah"

if not exist "%SCRIPT%" (
    echo ERROR: script not found: "%SCRIPT%"
    goto :failed
)

if not exist "%TORAH_IN%\*.txt" (
    echo ERROR: no input .txt files found in "%TORAH_IN%"
    goto :failed
)

if not exist "%TORAH_OUT%" mkdir "%TORAH_OUT%"
if errorlevel 1 goto :failed

for %%F in ("%TORAH_IN%\*.txt") do (
    call :process "%%~fF" "%%~nF"
    if errorlevel 1 goto :failed
)

echo.
echo DONE
pause
exit /b 0

:process
set "INPUT_FILE=%~1"
set "BASE_NAME=%~2"
set "BASE_NAME=%BASE_NAME:_raw=%"
echo Processing: %BASE_NAME%
py -3 "%SCRIPT%" "%INPUT_FILE%" "%TORAH_OUT%\%BASE_NAME%_taamim_annotated.txt"
exit /b %errorlevel%

:failed
echo.
echo FAILED
pause
exit /b 1
