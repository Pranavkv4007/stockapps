@echo off
cd /d "%~dp0\.."
call .venv\Scripts\activate
streamlit run FullScreener\Fullscreener_app.py
pause
