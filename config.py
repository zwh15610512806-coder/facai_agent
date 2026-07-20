"""应用配置管理"""
import os
from dotenv import load_dotenv

from integrations.settings import load_integration_settings

load_dotenv()

# 数据库配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/script_agent.db")

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "your-deepseek-api-key")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_V4_FLASH_MODEL = os.getenv("DEEPSEEK_V4_FLASH_MODEL", "deepseek-v4-flash")
DEEPSEEK_V4_PRO_MODEL = os.getenv("DEEPSEEK_V4_PRO_MODEL", "deepseek-v4-pro")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", DEEPSEEK_V4_FLASH_MODEL)
DEEPSEEK_REQUEST_TIMEOUT_SECONDS = float(os.getenv("DEEPSEEK_REQUEST_TIMEOUT_SECONDS", "40"))
INSPIRATION_AI_TIMEOUT_SECONDS = float(os.getenv("INSPIRATION_AI_TIMEOUT_SECONDS", "45"))
INSPIRATION_THINKING_AI_TIMEOUT_SECONDS = float(os.getenv("INSPIRATION_THINKING_AI_TIMEOUT_SECONDS", "240"))

# OpenAI-compatible LLM provider configuration
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "")
ARK_MODEL = os.getenv("ARK_MODEL", "")
DOUBAO_API_KEY = ARK_API_KEY or os.getenv("DOUBAO_API_KEY", "")
DOUBAO_BASE_URL = ARK_BASE_URL or os.getenv("DOUBAO_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_MODEL = ARK_MODEL or os.getenv("DOUBAO_MODEL") or "ep-20260703160153-h5cx5"

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M3")

GLM_API_KEY = os.getenv("GLM_API_KEY") or os.getenv("ZAI_API_KEY", "")
GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-5.2")

QWEN_API_KEY = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")

# ChromaDB 配置
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "viral_scripts")
CHROMA_COLLECTION_PRODUCTS = os.getenv("CHROMA_COLLECTION_PRODUCTS", "products")
CHROMA_COLLECTION_SCRIPTS = os.getenv("CHROMA_COLLECTION_SCRIPTS", "scripts")

# Embedding 模型配置
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER") or "volcengine_ark"
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME") or "ep-20260703164659-v5sh5"
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or ARK_API_KEY or DOUBAO_API_KEY
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL") or ARK_BASE_URL or DOUBAO_BASE_URL

# 应用配置
APP_TITLE = "抖音运营agent"
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
ALLOWED_HOSTS = [
    host.strip().lower()
    for host in os.getenv("ALLOWED_HOSTS", "").split(",")
    if host.strip()
]

# Ephemeral public tunnels use random subdomains. Keep the root domain itself
# excluded so this only admits a provider-issued tunnel hostname.
PUBLIC_TUNNEL_HOST_SUFFIXES = tuple(
    suffix.strip().lower()
    for suffix in os.getenv(
        "PUBLIC_TUNNEL_HOST_SUFFIXES", ".serveousercontent.com"
    ).split(",")
    if suffix.strip().startswith(".")
)
