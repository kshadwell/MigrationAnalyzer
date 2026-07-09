@echo off
title Colorado Migration Corridor Mapper - Setup
cd /d "%~dp0"
echo ============================================
echo  Colorado Migration Corridor Mapper - Setup
echo ============================================
echo.

:: Use specific Python path for machines without admin install
set PYTHON=C:\Program Files\Python313\python.exe

"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found at %PYTHON%
    pause
    exit /b 1
)

echo Python found:
"%PYTHON%" --version
echo.

:: Install dependencies
echo Installing required packages...
echo.
"%PYTHON%" -m pip install -r requirements.txt
echo.

if errorlevel 1 (
    echo.
    echo WARNING: Some packages may have failed to install.
    echo If you see errors above for rasterio, geopandas, or fiona,
    echo try installing them from conda-forge instead:
    echo.
    echo   conda install -c conda-forge rasterio geopandas fiona
    echo.
) else (
    echo.
    echo ============================================
    echo  Setup complete!
    echo ============================================
    echo.
    echo To start the app, double-click "Start App.bat"
    echo or run: python app\main.py
    echo.
)

pause
