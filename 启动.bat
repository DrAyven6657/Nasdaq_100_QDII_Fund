@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Nasdaq-100 Fund Monitor  -  daily update
echo ============================================

REM ---- Detect a Python that actually runs ----
REM Probe with -c instead of hard-coding a version: any 3.x works.
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PY=python"
    )
)

if not defined PY (
    echo.
    echo [ERROR] No working Python 3 found.
    echo Install Python 3 from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

echo Using Python: %PY%
for /f "delims=" %%v in ('%PY% -c "import sys;print(sys.version.split()[0], sys.executable)"') do echo   %%v

echo [1/2] Updating fund data ...
%PY% scrape.py
if errorlevel 1 (
    echo.
    echo [ERROR] Update failed. Details above.
    echo.
    pause
    exit /b 1
)

echo [2/2] Opening the page in your browser ...
start "" "%~dp0index.html"
echo.
echo Done! The page now shows the latest data.
echo Tip: double-click this file every day to refresh.
echo.
pause