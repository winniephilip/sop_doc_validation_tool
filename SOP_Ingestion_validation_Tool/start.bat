@echo off
cd /d "%~dp0"

echo Installing Python dependencies...
pip install -r requirements.txt
echo.

echo Checking for Tesseract OCR (required for Doc vs Screenshot)...
tesseract --version >nul 2>&1
if not errorlevel 1 goto tesseract_ok

echo.
echo [WARNING] Tesseract OCR is NOT installed.
echo           The "Doc vs Screenshot" feature will not work without it.
echo.
echo           Download and install Tesseract for Windows:
echo           https://github.com/UB-Mannheim/tesseract/wiki
echo.
echo           After installing, re-run start.bat.
echo           Doc vs Doc and Doc vs Webpage will still work now.
echo.
pause
goto start_server

:tesseract_ok
echo Tesseract found: OK
echo.

:start_server
echo Starting SOP Validation Tool at http://localhost:8000
echo.
set PYTHONPATH=%~dp0
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
