@echo off
title RepoChat
echo ========================================================
echo Starting RepoChat in Virtual Environment...
echo ========================================================
cd /d "%~dp0"
call "%~dp0.venv\Scripts\activate.bat"
streamlit run "%~dp0app.py" --server.fileWatcherType none
pause
