@echo off
echo ============================================
echo   Stock Analysis Hub - Starting...
echo ============================================

cd /d "%~dp0backend"

echo Installing Python dependencies...
pip install -r requirements.txt --quiet

echo.
echo Starting server...
cd /d "%~dp0"
start "" http://localhost:8000
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
