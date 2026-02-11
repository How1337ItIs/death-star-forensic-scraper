@echo off
TITLE Death Star Mission Control
CLS

ECHO ========================================================
ECHO       DEATH STAR FORENSIC SCRAPER - MISSION CONTROL
ECHO ========================================================
ECHO.

:: 1. Check for Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO [ERROR] Python is not installed. Please install Python 3.10+ from python.org
    PAUSE
    EXIT /B
)

:: 2. Create Venv if missing
IF NOT EXIST "venv" (
    ECHO [INFO] Creating virtual environment...
    python -m venv venv
)

:: 3. Activate Venv
CALL venv\Scripts\activate.bat

:: 4. Install requirements
ECHO [INFO] Checking dependencies...
pip install -r requirements.txt

:: 5. Install Playwright browsers
ECHO [INFO] Verifying browser binaries...
playwright install chromium

:: 6. Launch
ECHO.
ECHO [SUCCESS] Systems Online.
ECHO [INFO] Opening Dashboard at http://localhost:8765...
START http://localhost:8765

ECHO [INFO] Starting Server...
uvicorn dashboard:app --host 0.0.0.0 --port 8765

PAUSE
