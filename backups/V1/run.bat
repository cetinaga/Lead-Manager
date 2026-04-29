@echo off
setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

REM Prefer local venv Python
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo Using Python: %PY%

REM Ensure core deps are installed (only installs if import fails)
"%PY%" -c "import uvicorn, fastapi, jinja2" >NUL 2>&1
if errorlevel 1 (
  echo Installing dependencies from requirements.txt ...
  "%PY%" -m pip install -r requirements.txt || (
    echo Failed to install dependencies. Aborting.
    exit /b 1
  )
)

REM Config
set "HOST=127.0.0.1"
set "PORT=8000"
REM Set RELOAD=1 to enable autoreload (can be unstable on OneDrive)
if "%RELOAD%"=="" set "RELOAD=0"
set "RELOAD_ARG="
if "%RELOAD%"=="1" (
  REM Mit Reload: stabiler auf Netz/Cloud-Laufwerken
  set "WATCHFILES_FORCE_POLLING=1"
  set "RELOAD_ARG=--reload --reload-include *.py --reload-exclude .venv --reload-exclude *.db --reload-exclude *.log --reload-exclude ~$*"
)
set "URL=http://%HOST%:%PORT%/"

REM Start server in a new window so this script can continue
start "LeadManager Server" cmd /k "%PY%" -m uvicorn main:app --host %HOST% --port %PORT% %RELOAD_ARG%

echo Waiting for server to become ready at %URL% ...
powershell -NoProfile -Command "try{for($i=0;$i -lt 30;$i++){try{$r=Invoke-WebRequest -Uri '%URL%health' -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop;if($r.StatusCode -eq 200){exit 0}}catch{}; Start-Sleep -Milliseconds 500}; exit 1}catch{exit 1}"
if %ERRORLEVEL% EQU 0 (
  echo Opening browser: %URL%
  start "" "%URL%"
  exit /b 0
) else (
  echo Server noch nicht erreichbar. Oeffne Startseite trotzdem ...
  start "" "%URL%"
  exit /b 0
)

endlocal
