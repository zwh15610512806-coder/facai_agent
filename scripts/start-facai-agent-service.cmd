@echo off
setlocal
cd /d "%~dp0.."
set "PYTHONUTF8=1"

set "PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [ERROR] Project virtual environment is missing.
    echo Run: powershell -ExecutionPolicy Bypass -File scripts\bootstrap-venv.ps1
    exit /b 1
)

"%PYTHON%" "%~dp0verify_runtime.py" || exit /b 1
"%PYTHON%" "%~dp0facai_agent_service.py" --port 8001
