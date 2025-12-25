@echo off
echo ╔════════════════════════════════════════════════╗
echo ║      Outpaint API Server - Starting...        ║
echo ╚════════════════════════════════════════════════╝
echo.

REM Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv venv
    pause
    exit /b 1
)

REM Activate venv
call venv\Scripts\activate.bat

REM Check if API dependencies are installed
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo [INFO] Installing API dependencies...
    pip install -r requirements_api.txt
)

REM Kill any existing process on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo [INFO] Killing existing process on port 8000 (PID: %%a^)
    taskkill /PID %%a /F >nul 2>&1
)

REM Start the API server
echo [INFO] Starting API server on http://localhost:8000
echo [INFO] API docs available at: http://localhost:8000/docs
echo.
python api_server.py --host 0.0.0.0 --port 8000

pause
