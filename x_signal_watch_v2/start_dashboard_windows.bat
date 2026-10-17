@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Installation absente. Lancez d'abord start_demo_windows.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run dashboard.py
pause
