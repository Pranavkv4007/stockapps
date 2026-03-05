@echo off
echo Starting MyHoldings Portfolio App...
cd /d "%~dp0"

REM Activate venv if available
if exist "..\\.venv\\Scripts\\activate.bat" (
    call "..\\.venv\\Scripts\\activate.bat"
)

REM Install deps if needed
pip install streamlit plotly pandas python-dotenv openai google-genai beautifulsoup4 requests >nul 2>&1

REM Launch
start http://localhost:8501
streamlit run MyHoldingsApp.py
pause
