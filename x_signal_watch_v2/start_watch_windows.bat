@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Installation absente. Lancez d'abord start_demo_windows.bat.
    pause
    exit /b 1
)
if not exist ".env" (
    echo Configurez les identifiants X et les cles API dans .env avant de lancer la veille.
    pause
    exit /b 1
)
echo Demarrage de la collecte X et de la deduplication IA...
".venv\Scripts\python.exe" main.py watch
pause
