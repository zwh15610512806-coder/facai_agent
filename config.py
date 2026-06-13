"""应用配置管理"""
import os
from dotenv import load_dotenv

load_dotenv()

# 数据库配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/script_agent.db")

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "your-deepseek-api-key")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ChromaDB 配置
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "viral_scripts")
CHROMA_COLLECTION_PRODUCTS = os.getenv("CHROMA_COLLECTION_PRODUCTS", "products")
CHROMA_COLLECTION_SCRIPTS = os.getenv("CHROMA_COLLECTION_SCRIPTS", "scripts")

# Embedding 模型配置
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5")

# 应用配置
APP_TITLE = "法采新媒体运营 Agent"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "抖音短视频带货脚本智能生成系统"

# Flask 检索后端代理
SEARCH_BACKEND_URL = os.getenv("SEARCH_BACKEND_URL", "http://127.0.0.1:5000")

# 文件上传配置
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

# Web access controls
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
