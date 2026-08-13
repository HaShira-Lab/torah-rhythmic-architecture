@echo off
setlocal

rem Resolve every path from this launcher's location, not from the caller's CWD.
set "REPO_ROOT=%~dp0.."
set "SCRIPT=%REPO_ROOT%\src\preprocessing\download_torah.py"
set "OUTDIR=%REPO_ROOT%\data\data_raw\torah"

echo === PREPROCESSING: DOWNLOAD TORAH RAW ===

python "%SCRIPT%" ^
  --books Genesis Exodus Leviticus Numbers Deuteronomy ^
  --version-name "Tanach_with_Ta'amei_Hamikra" ^
  --outdir "%OUTDIR%"

if errorlevel 1 (
  echo.
  echo FAILED
  pause
  exit /b 1
)

echo.
echo DONE
pause
exit /b 0
