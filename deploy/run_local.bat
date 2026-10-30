@echo off
setlocal
cd /d "%~dp0\.."
title AgriSmoke AI - Full Stack Platform Launcher
color 0A

echo ==============================================================================
echo                 [ AgriSmoke AI Platform Launcher ]
echo       Crop-Burning and Urban Air Quality Prediction System (Delhi-NCR)
echo ==============================================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not added to your PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/4] Checking Python environment...
python --version

:: 2. Initialize SQLite Database
echo.
echo [2/4] Verifying and Initializing SQLite Database...
python database/init_db.py
if errorlevel 1 (
    echo [ERROR] Database initialization failed.
    pause
    exit /b 1
)

:: 3. Check / Train Machine Learning Model
echo.
echo [3/4] Checking Machine Learning Model Artifacts...
if not exist "ai-ml\models\aqi_dispersion_model.joblib" (
    echo Training Machine Learning Model...
    python ai-ml/train_model.py
) else (
    echo ML model artifacts found in ai-ml\models\.
)

:: 4. Launch FastAPI Backend
echo.
echo [4/4] Starting FastAPI Backend on http://127.0.0.1:8000 ...
echo - Web Dashboard: http://127.0.0.1:8000
echo - Swagger API Documentation: http://127.0.0.1:8000/docs
echo.
echo Press Ctrl+C in this console to stop the server.
echo ==============================================================================
python backend/run.py
pause
