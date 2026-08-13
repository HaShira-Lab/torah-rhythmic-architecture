@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SOURCE=data\data_processed\torah"
set "SCRIPT=src\tools\rhyme\export_rhyme_groups_window.py"
set "OUT=results\tools\export_rhyme_groups_window"

if "%~1"=="" goto usage

echo === EXPORT RHYME GROUPS WINDOW ===
python "%SCRIPT%" ^
  --source-dir "%SOURCE%" ^
  --out-dir "%OUT%" ^
  %*

if errorlevel 1 exit /b 1
echo EXPORT COMPLETED.
endlocal
exit /b 0

:usage
echo Usage:
echo   run\export_rhyme_groups_window.bat --book BOOK [options]
echo.
echo Example:
echo   run\export_rhyme_groups_window.bat --book genesis --start-verse-ordinal 1 --verse-count 30
endlocal
exit /b 2
