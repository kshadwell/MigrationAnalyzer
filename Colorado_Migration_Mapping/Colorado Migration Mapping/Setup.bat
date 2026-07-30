@echo off
title Colorado Migration Corridor Mapper - Setup
cd /d "%~dp0"
echo ============================================
echo  Colorado Migration Corridor Mapper - Setup
echo ============================================
echo.

:: ==================================================================
:: Step 1 -- External environmental data
:: ==================================================================

if exist "%~dp0environment_data\elevation" (
    echo [1/4] Environmental data already installed -- skipping.
    echo.
    goto pip_setup
)

set "ZIPFILE=Ext_FilesForMigrationAnalyzer.zip"
if not exist "%ZIPFILE%" (
    echo [1/4] External data not found.
    echo.
    echo   The app needs environmental reference data for
    echo   elevation, snow, and road-crossing features.
    echo.
    echo   To install it:
    echo     1. Download Ext_FilesForMigrationAnalyzer.zip from Dropbox
    echo     2. Place the zip in this folder:
    echo        %~dp0
    echo     3. Re-run Setup.bat
    echo.
    echo   The app will still launch without it, but environmental
    echo   sampling features will be unavailable.
    echo.
    goto pip_setup
)

echo [1/4] Extracting environmental data...
echo       This is about 19 GB -- it may take 10-20 minutes.
echo.
tar -xf "%ZIPFILE%"
if errorlevel 1 (
    echo.
    echo ERROR: Extraction failed. The zip may be corrupt or incomplete.
    pause
    exit /b 1
)

if exist "Ext_FilesForMigrationAnalyzer" (
    ren "Ext_FilesForMigrationAnalyzer" environment_data
)

if exist "environment_data\elevation" (
    echo       Environmental data installed successfully.
    echo.
    echo       You can delete Ext_FilesForMigrationAnalyzer.zip to
    echo       free up disk space. The extracted data is all you need.
    echo.
) else (
    echo.
    echo WARNING: Extraction finished but expected files not found.
    echo.
)

:: ==================================================================
:: Step 2 -- Python + pip
:: ==================================================================
:pip_setup

set "PYTHON=%~dp0python-3.13\python.exe"

"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Bundled Python not found at %PYTHON%
    echo Make sure the python-3.13 folder exists next to this file.
    pause
    exit /b 1
)

echo [2/4] Python found:
"%PYTHON%" --version
echo.

"%PYTHON%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo       pip not found -- installing it now...
    echo.
    curl -sL -o "%~dp0python-3.13\get-pip.py" https://bootstrap.pypa.io/get-pip.py
    if errorlevel 1 (
        echo ERROR: Could not download get-pip.py.
        pause
        exit /b 1
    )
    "%PYTHON%" "%~dp0python-3.13\get-pip.py" --no-warn-script-location
    del "%~dp0python-3.13\get-pip.py"
    echo.
)

:: ==================================================================
:: Step 3 -- Install Python packages
:: ==================================================================
echo [3/4] Installing required packages...
echo.
"%PYTHON%" -m pip install --target "%~dp0python-3.13\Lib\site-packages" -r requirements.txt --no-warn-script-location
echo.

if errorlevel 1 (
    echo WARNING: Some packages may have failed to install.
    echo.
)

:: ==================================================================
:: Step 4 -- Desktop shortcut
:: ==================================================================
echo [4/4] Creating desktop shortcut...

set "SHORTCUT=%USERPROFILE%\Desktop\Migration Corridor Mapper.lnk"
set "TARGET=%~dp0Start App.bat"

:: Elk icon. Falls back to a generic Windows icon if the file is missing,
:: so a stripped-down copy of the folder still gets a working shortcut.
set "ICONFILE=%~dp0app\assets\favicon.ico"
set "ICONIDX=0"
if not exist "%ICONFILE%" (
    set "ICONFILE=%SystemRoot%\System32\SHELL32.dll"
    set "ICONIDX=14"
)

powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%ICONFILE%,%ICONIDX%'; $s.Description='Colorado Migration Corridor Mapper'; $s.Save()"

if exist "%SHORTCUT%" (
    echo       Desktop shortcut created.
) else (
    echo       Could not create shortcut -- you can still launch
    echo       the app by double-clicking Start App.bat directly.
)
echo.

echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo  To start the app:
echo    - Double-click "Migration Corridor Mapper" on your Desktop
echo    - Or double-click "Start App.bat" in this folder
echo.

pause
