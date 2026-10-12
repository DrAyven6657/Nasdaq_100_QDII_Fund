@echo off
cd /d "%~dp0"
echo ============================================
echo   Nasdaq-100 Fund Monitor  -  daily update
echo ============================================

REM ---- Auto-detect Python ----
set "PY="
if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
if not defined PY ( where py >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( where python >nul 2>nul && set "PY=python" )

if not defined PY (
    echo.
    echo [ERROR] Python not found. Please install Python 3.12+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Using Python: %PY%
echo [1/2] Updating fund data ...
%PY% scrape.py
if errorlevel 1 (
    echo.
    echo [ERROR] Update failed. Check your network and try again.
    pause
    exit /b 1
)
echo [2/2] Opening the page in your browser ...
start "" "%~dp0index.html"
echo.
echo Done! The page now shows the latest data.
echo Tip: double-click this file every day to refresh.
timeout /t 4 >nul
