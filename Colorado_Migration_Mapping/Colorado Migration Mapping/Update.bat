@echo off
setlocal EnableDelayedExpansion
title Colorado Migration Corridor Mapper - Update

echo ============================================
echo  Colorado Migration Corridor Mapper - Update
echo ============================================
echo.
echo  Updates an EXISTING install with this newer
echo  version. Your environmental data and saved
echo  sessions are left alone.
echo.

set "SOURCE=%~dp0"
if "%SOURCE:~-1%"=="\" set "SOURCE=%SOURCE:~0,-1%"

:: ==================================================================
:: Step 1 -- Find the existing install
:: ==================================================================
echo [1/4] Locating your current install...

set "INSTALL="
set "LNK=%USERPROFILE%\Desktop\Migration Corridor Mapper.lnk"

if exist "%LNK%" (
    for /f "usebackq delims=" %%i in (`
        powershell -NoProfile -Command ^
        "$w=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%').WorkingDirectory; if($w){$w.TrimEnd('\')}"
    `) do set "INSTALL=%%i"
)

if defined INSTALL (
    if exist "!INSTALL!\Start App.bat" (
        echo       Found via your desktop shortcut:
        echo       !INSTALL!
    ) else (
        set "INSTALL="
    )
)

if not defined INSTALL (
    echo       Could not find it automatically.
    echo.
    echo       Enter the full path to your existing
    echo       "Colorado Migration Mapping" folder
    echo       -- the one containing Start App.bat.
    echo.
    set /p "INSTALL=Path: "
    if defined INSTALL if "!INSTALL:~-1!"=="\" set "INSTALL=!INSTALL:~0,-1!"
)

if not exist "!INSTALL!\Start App.bat" (
    echo.
    echo ERROR: No install found at:
    echo   !INSTALL!
    echo.
    echo That folder must contain Start App.bat. If you have
    echo never installed the app, run Setup.bat instead.
    echo.
    pause
    exit /b 1
)

:: Refuse to update a folder onto itself.
if /i "!INSTALL!"=="%SOURCE%" (
    echo.
    echo ERROR: That is this same folder. Run Update.bat from the
    echo newly downloaded copy, not from your install.
    echo.
    pause
    exit /b 1
)

echo.

:: ==================================================================
:: Step 2 -- Confirm
:: ==================================================================
echo [2/4] About to update:
echo         !INSTALL!
echo       with the newer files in:
echo         %SOURCE%
echo.
echo       Left untouched: environment_data\ (your ~19 GB of
echo       elevation/snow/road data) and app\session_data\
echo       (your saved sessions).
echo.
set /p "OK=Proceed? (Y/N): "
if /i not "!OK!"=="Y" (
    echo.
    echo Cancelled -- nothing was changed.
    echo.
    pause
    exit /b 0
)
echo.

:: ==================================================================
:: Step 3 -- Back up the current code
:: ==================================================================
echo [3/4] Backing up your current app folder...

for /f "usebackq delims=" %%i in (`
    powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"
`) do set "STAMP=%%i"

set "BACKUP=!INSTALL!\_backup_!STAMP!"
robocopy "!INSTALL!\app" "!BACKUP!\app" /E /XD session_data /NFL /NDL /NJH /NJS /NP >nul
if exist "!INSTALL!\Setup.bat"  copy /y "!INSTALL!\Setup.bat"  "!BACKUP!\" >nul
if exist "!INSTALL!\Update.bat" copy /y "!INSTALL!\Update.bat" "!BACKUP!\" >nul

if exist "!BACKUP!\app\main.py" (
    echo       Saved to: _backup_!STAMP!\
    echo       Delete that folder once you are happy with the update.
) else (
    echo       WARNING: backup may be incomplete -- continuing anyway.
)
echo.

:: ==================================================================
:: Step 4 -- Copy the new files in
:: ==================================================================
echo [4/4] Copying new files...
echo       Only changed files are transferred, so this is
echo       usually quick.
echo.

:: No /MIR and no /PURGE: robocopy will never delete anything in the
:: destination, so environment_data\ and session_data\ are safe even
:: though they do not exist here in the source.
robocopy "%SOURCE%" "!INSTALL!" /E /XD environment_data session_data /NFL /NDL /NJH /NP

if !ERRORLEVEL! GEQ 8 (
    echo.
    echo ERROR: The copy failed. Your old files are still in place,
    echo and a backup is in _backup_!STAMP!\
    echo.
    echo If the app was running, close it and try again.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Update complete^^!
echo ============================================
echo.
echo  Launch as usual:
echo    - "Migration Corridor Mapper" on your Desktop
echo    - or Start App.bat in your install folder
echo.
echo  Your environmental data and saved sessions were
echo  not touched.
echo.

pause

:: robocopy uses 0-7 for success, so don't let its exit code leak out
:: and look like a failure to whatever launched this.
exit /b 0
