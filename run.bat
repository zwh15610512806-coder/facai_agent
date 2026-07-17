@echo off
chcp 65001 >nul
echo ========================================
echo   短视频脚本生成 Agent
echo ========================================
echo.

set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [ERROR] 未找到项目专用虚拟环境。
    echo 请先运行: powershell -ExecutionPolicy Bypass -File scripts\bootstrap-venv.ps1
    exit /b 1
)

"%PYTHON%" scripts\verify_runtime.py || exit /b 1

REM 检查 .env 文件
if not exist .env (
    echo [ERROR] 未找到 .env。请复制 .env.example，并配置所需的 AI 服务密钥。
    exit /b 1
)

REM 只在数据库不存在时才初始化（避免每次启动清空数据）
if not exist "data\script_agent.db" (
    echo [1/2] 首次运行，初始化数据库...
    "%PYTHON%" seed_all.py
    echo.
) else (
    echo [1/2] 数据库已存在，跳过初始化
    echo.
)

REM 启动服务
echo [2/2] 启动服务...
echo.
echo   访问地址: http://localhost:8001/app
echo.
"%PYTHON%" main.py
pause
