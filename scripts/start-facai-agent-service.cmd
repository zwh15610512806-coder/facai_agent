@echo off
setlocal
cd /d "%~dp0.."

set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" "%~dp0facai_agent_service.py" --port 8001
