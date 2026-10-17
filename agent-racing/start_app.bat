@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install.bat
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" -m evolution_lab serve --open-browser
if errorlevel 1 (
  echo L'application n'a pas pu demarrer. Si elle est deja ouverte, consultez http://127.0.0.1:8765
  pause
)
