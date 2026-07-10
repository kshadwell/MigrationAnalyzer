@echo off
title Colorado Migration Corridor Mapper - Setup
cd /d "%~dp0"
echo ============================================
echo  Colorado Migration Corridor Mapper - Setup
echo ============================================
echo.

:: Use the bundled embeddable Python (ships with the repo)
set PYTHON=%~dp0python-3.13\python.exe

"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Bundled Python not found at %PYTHON%
    echo Make sure the python-3.13 folder exists next to this file.
    pause
    exit /b 1
)

echo Python found:
"%PYTHON%" --version
echo.

:: Bootstrap pip if not already installed
"%PYTHON%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo pip not found — installing it now...
    echo.
    curl -sL -o "%~dp0python-3.13\get-pip.py" https://bootstrap.pypa.io/get-pip.py
    if errorlevel 1 (
        echo ERROR: Could not download get-pip.py. Check your internet connection.
        pause
        exit /b 1
    )
    "%PYTHON%" "%~dp0python-3.13\get-pip.py" --no-warn-script-location
    del "%~dp0python-3.13\get-pip.py"
    echo.
)

:: Install dependencies into the bundled Python's own site-packages
echo Installing required packages...
echo.
"%PYTHON%" -m pip install --target "%~dp0python-3.13\Lib\site-packages" -r requirements.txt --no-warn-script-location
echo.

if errorlevel 1 (
    echo.
    echo WARNING: Some packages may have failed to install.
    echo Check the output above for errors.
    echo.
) else (
    echo.
    echo ============================================
    echo  Setup complete!
    echo ============================================
    echo.
    echo To start the app, double-click "Start App.bat"
    echo.
)

pause
