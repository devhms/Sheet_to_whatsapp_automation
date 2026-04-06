@echo off
echo ============================================
echo Jamiat Management System - Setup
echo ============================================
echo.

cd /d "%~dp0"

echo [1/4] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

echo.
echo [2/4] Creating virtual environment...
if exist "venv" (
    echo [SKIP] Virtual environment already exists
) else (
    python -m venv venv
    echo [OK] Virtual environment created
)

echo.
echo [3/4] Installing dependencies...
call venv\Scripts\activate
pip install -r requirements.txt --quiet
echo [OK] Dependencies installed

echo.
echo [4/4] Checking configuration...
if not exist "config.json" (
    echo [ERROR] config.json not found!
    pause
    exit /b 1
)
if not exist "service_account.json" (
    echo [WARNING] service_account.json not found!
    echo Please add your Google service account credentials.
    echo See: https://console.cloud.google.com/apis/credentials
)
if not exist ".env" (
    echo [WARNING] .env file not found!
    echo Copy .env.example to .env and fill in your values.
    copy .env.example .env >nul
    echo Created .env from .env.example
)

echo.
echo ============================================
echo Setup complete!
echo ============================================
echo.
echo Next steps:
echo 1. Edit .env with your credentials
echo 2. Edit config.json with your sheet URL and targets
echo 3. Run: run_bot.bat
echo.
pause
