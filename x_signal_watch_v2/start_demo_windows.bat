@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv 2>nul
    if errorlevel 1 python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo Impossible de creer le venv. Installer Python 3.11 ou 3.12.
    pause
    exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Erreur d'installation des dependances.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py demo
if errorlevel 1 (
    pause
    exit /b 1
)
echo Overture du tableau de bord Streamlit...
".venv\Scripts\python.exe" -m streamlit run dashboard.py
pause
