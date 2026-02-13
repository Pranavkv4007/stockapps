@echo off
cd /d "%~dp0\.."
call .venv\Scripts\activate
streamlit run individual\app.py
pause
