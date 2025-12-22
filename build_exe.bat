@echo off
setlocal

:: ============================================================
::  Kling UI - Build Executable
::  Creates a standalone .exe using PyInstaller
:: ============================================================

echo.
echo ============================================
echo   Kling UI - Build Executable
echo ============================================
echo.

:: Get script directory
set SCRIPT_DIR=%~dp0

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

:: Check/install PyInstaller
echo [1/4] Checking PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

:: Install dependencies needed for build
echo [2/4] Installing build dependencies...
pip install requests Pillow rich tkinterdnd2 selenium webdriver-manager --quiet

:: Clean previous builds
echo [3/4] Cleaning previous builds...
if exist "%SCRIPT_DIR%build" rmdir /s /q "%SCRIPT_DIR%build"
if exist "%SCRIPT_DIR%dist\KlingUI" rmdir /s /q "%SCRIPT_DIR%dist\KlingUI"

:: Build the executable
echo [4/4] Building executable...
echo.
cd /d "%SCRIPT_DIR%"
pyinstaller kling_ui.spec --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo ============================================
    echo   BUILD FAILED
    echo ============================================
    echo Check the errors above for details.
    pause
    exit /b 1
)

:: Copy additional files to dist folder
echo.
echo Copying additional files...
if not exist "%SCRIPT_DIR%dist\KlingUI" mkdir "%SCRIPT_DIR%dist\KlingUI"

:: Copy Python source files that might be imported at runtime
copy "%SCRIPT_DIR%kling_generator_falai.py" "%SCRIPT_DIR%dist\KlingUI\" >nul 2>&1
copy "%SCRIPT_DIR%dependency_checker.py" "%SCRIPT_DIR%dist\KlingUI\" >nul 2>&1

:: Copy the kling_gui folder
if exist "%SCRIPT_DIR%kling_gui" (
    if not exist "%SCRIPT_DIR%dist\KlingUI\kling_gui" mkdir "%SCRIPT_DIR%dist\KlingUI\kling_gui"
    xcopy "%SCRIPT_DIR%kling_gui\*.py" "%SCRIPT_DIR%dist\KlingUI\kling_gui\" /y >nul 2>&1
)

:: Create a launcher batch file for the built exe
echo @echo off > "%SCRIPT_DIR%dist\KlingUI\Run_KlingUI.bat"
echo cd /d "%%~dp0" >> "%SCRIPT_DIR%dist\KlingUI\Run_KlingUI.bat"
echo start "" "KlingUI.exe" >> "%SCRIPT_DIR%dist\KlingUI\Run_KlingUI.bat"

echo.
echo ============================================
echo   BUILD SUCCESSFUL!
echo ============================================
echo.
echo Output location: %SCRIPT_DIR%dist\KlingUI\
echo.
echo Files created:
echo   - KlingUI.exe (main executable)
echo   - Run_KlingUI.bat (launcher)
echo.
echo To distribute:
echo   1. Copy the entire 'dist\KlingUI' folder
echo   2. Users run KlingUI.exe or Run_KlingUI.bat
echo.
echo NOTE: First run will create kling_config.json for settings
echo.

:: Open the output folder
explorer "%SCRIPT_DIR%dist\KlingUI"

pause
endlocal
