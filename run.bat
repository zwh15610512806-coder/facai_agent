@echo off
chcp 65001 >nul
echo ========================================
echo   短视频脚本生成 Agent
echo ========================================
echo.

set PYTHON="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

REM 检查 .env 文件
if not exist .env (
    echo [!] 未找到 .env 文件，正在创建...
    echo DEEPSEEK_API_KEY=your-deepseek-api-key-here > .env
    echo DEEPSEEK_BASE_URL=https://api.deepseek.com >> .env
    echo DEEPSEEK_MODEL=deepseek-chat >> .env
    echo DATABASE_URL=sqlite:///./data/script_agent.db >> .env
    echo CHROMA_PERSIST_DIR=./data/chroma_db >> .env
    echo [OK] .env 文件已创建，请编辑填入你的 DeepSeek API Key
)

REM 只在数据库不存在时才初始化（避免每次启动清空数据）
if not exist "data\script_agent.db" (
    echo [1/2] 首次运行，初始化数据库...
    %PYTHON% seed_all.py
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
%PYTHON% main.py
pause
