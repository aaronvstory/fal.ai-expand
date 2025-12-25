@echo off
setlocal

:: ============================================================
::  Outpaint UI - Build Executable
::  Creates a standalone .exe using PyInstaller
:: ============================================================

echo.
echo ============================================
echo   Outpaint UI - Build Executable
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
pip install requests Pillow pydantic rich tkinterdnd2 selenium webdriver-manager --quiet

:: Clean previous builds
echo [3/4] Cleaning previous builds...
if exist "%SCRIPT_DIR%build" rmdir /s /q "%SCRIPT_DIR%build"
if exist "%SCRIPT_DIR%dist\OutpaintUI" rmdir /s /q "%SCRIPT_DIR%dist\OutpaintUI"

:: Build the executable
echo [4/4] Building executable...
echo.
cd /d "%SCRIPT_DIR%"
pyinstaller outpaint_ui.spec --noconfirm

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
if not exist "%SCRIPT_DIR%dist\OutpaintUI" mkdir "%SCRIPT_DIR%dist\OutpaintUI"

:: Copy Python source files that might be imported at runtime
copy "%SCRIPT_DIR%outpaint_generator.py" "%SCRIPT_DIR%dist\OutpaintUI\" >nul 2>&1
copy "%SCRIPT_DIR%outpaint_config.py" "%SCRIPT_DIR%dist\OutpaintUI\" >nul 2>&1
copy "%SCRIPT_DIR%outpaint_diagnostics.py" "%SCRIPT_DIR%dist\OutpaintUI\" >nul 2>&1
copy "%SCRIPT_DIR%dependency_checker.py" "%SCRIPT_DIR%dist\OutpaintUI\" >nul 2>&1

:: Copy packages and workflow templates
if exist "%SCRIPT_DIR%outpaint_gui" (
    if not exist "%SCRIPT_DIR%dist\OutpaintUI\outpaint_gui" mkdir "%SCRIPT_DIR%dist\OutpaintUI\outpaint_gui"
    xcopy "%SCRIPT_DIR%outpaint_gui\*.py" "%SCRIPT_DIR%dist\OutpaintUI\outpaint_gui\" /y >nul 2>&1
)

if exist "%SCRIPT_DIR%backends" (
    if not exist "%SCRIPT_DIR%dist\OutpaintUI\backends" mkdir "%SCRIPT_DIR%dist\OutpaintUI\backends"
    xcopy "%SCRIPT_DIR%backends\*.py" "%SCRIPT_DIR%dist\OutpaintUI\backends\" /y >nul 2>&1
)

if exist "%SCRIPT_DIR%comfyui_workflows" (
    if not exist "%SCRIPT_DIR%dist\OutpaintUI\comfyui_workflows" mkdir "%SCRIPT_DIR%dist\OutpaintUI\comfyui_workflows"
    xcopy "%SCRIPT_DIR%comfyui_workflows\*.json" "%SCRIPT_DIR%dist\OutpaintUI\comfyui_workflows\" /y >nul 2>&1
)

:: Create a launcher batch file for the built exe
echo @echo off > "%SCRIPT_DIR%dist\OutpaintUI\Run_OutpaintUI.bat"
echo cd /d "%%~dp0" >> "%SCRIPT_DIR%dist\OutpaintUI\Run_OutpaintUI.bat"
echo start "" "OutpaintUI.exe" >> "%SCRIPT_DIR%dist\OutpaintUI\Run_OutpaintUI.bat"

echo.
echo ============================================
echo   BUILD SUCCESSFUL!
echo ============================================
echo.
echo Output location: %SCRIPT_DIR%dist\OutpaintUI\
echo.
echo Files created:
echo   - OutpaintUI.exe (main executable)
echo   - Run_OutpaintUI.bat (launcher)
echo.
echo To distribute:
echo   1. Copy the entire 'dist\OutpaintUI' folder
echo   2. Users run OutpaintUI.exe or Run_OutpaintUI.bat
echo.
echo NOTE: First run will create outpaint_config.json for settings
echo.

:: Open the output folder
explorer "%SCRIPT_DIR%dist\OutpaintUI"

pause
endlocal
