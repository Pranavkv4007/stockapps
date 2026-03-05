@echo off
echo ============================================
echo  Concall Transcript Scorer (RAG)
echo ============================================
echo.
echo Place your concall transcript files (.txt or .pdf) in:
echo   %~dp0transcripts\
echo.
echo Opening transcripts folder...
if not exist "%~dp0transcripts" mkdir "%~dp0transcripts"
start "" "%~dp0transcripts"
echo.
echo Launching app...
cd /d "%~dp0\.."
call .venv\Scripts\activate
streamlit run individual\IndividualStockApp.py
pause
