@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 ou plus recent est requis. Installez-le depuis https://www.python.org/downloads/ en cochant Add Python to PATH.
  pause
  exit /b 1
)
python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 minimum requis'"
if errorlevel 1 goto :failure
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto :failure
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failure
".venv\Scripts\python.exe" -m evolution_lab doctor
if errorlevel 1 goto :failure
echo Installation terminee. Double-cliquez sur start_app.bat.
pause
exit /b 0
:failure
echo Installation incomplete. Verifiez votre connexion Internet et le message ci-dessus.
pause
exit /b 1
