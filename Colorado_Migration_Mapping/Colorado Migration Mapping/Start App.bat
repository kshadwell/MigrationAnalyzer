@echo off
title Colorado Migration Corridor Mapper
cd /d "%~dp0"

set "PYTHON=C:\Program Files\Python313\python.exe"
set "URL=http://127.0.0.1:8050/"

if not exist "%PYTHON%" (
    echo.
    echo ERROR: Python not found at:
    echo   %PYTHON%
    echo.
    echo Please run Setup.bat first, or install Python 3.13 from python.org.
    echo.
    pause
    exit /b 1
)

rem If something is already listening on 8050, just open the browser and exit.
netstat -ano | findstr ":8050 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo App is already running. Opening browser...
    start "" "%URL%"
    exit /b 0
)

echo Starting Colorado Migration Corridor Mapper...
echo (The browser will open automatically once the app is ready.)
echo.

rem Launch Python in a separate window so this one can poll for readiness
rem and so the app keeps running if the user closes the browser.
start "Colorado Migration Mapper - Server" "%PYTHON%" app\main.py

rem Poll the server up to ~60 seconds. curl ships with Windows 10+.
set /a tries=0
:wait_loop
set /a tries+=1
curl -s -o nul -m 1 "%URL%" >nul 2>&1
if not errorlevel 1 goto ready
if %tries% GEQ 60 goto timeout
timeout /t 1 /nobreak >nul
goto wait_loop

:ready
echo Ready. Opening browser at %URL%
start "" "%URL%"
exit /b 0

:timeout
echo.
echo ERROR: The app did not start within 60 seconds.
echo Check the "Colorado Migration Mapper - Server" window for an error message.
echo.
pause
exit /b 1
