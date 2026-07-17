"""应用配置管理"""
import ipaddress
import os
import re
from dotenv import load_dotenv

from integrations.settings import load_integration_settings

load_dotenv()


def _strict_positive_env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    if not raw_value.isascii() or not raw_value.isdigit():
        raise ValueError(f"{name} must be a positive integer")
    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _bounded_positive_env_int(name: str, default: int, *, maximum: int) -> int:
    value = _strict_positive_env_int(name, default)
    if value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _exact_provider_hostname(value: str, *, name: str) -> str:
    """Return an IDNA-normalized administrator-supplied hostname only.

    Provider records never get to choose these values: accepting a URL, a
    wildcard, a path, or an IP literal here would weaken the network policy
    before the provider transport gets a chance to validate an origin.
    """

    candidate = value.strip()
    if not candidate or candidate != value or any(
        marker in candidate for marker in ("*", ":", "/", "?", "#", "@", "[", "]", "\\")
    ):
        raise ValueError(f"{name} must contain exact hostnames only")
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        pass
    else:
        raise ValueError(f"{name} must not contain IP addresses")
    try:
        hostname = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError(f"{name} contains an invalid hostname") from exc
    labels = hostname.split(".")
    if (
        len(hostname) > 253
        or len(labels) < 2
        or any(not _HOST_LABEL.fullmatch(label) for label in labels)
        or re.fullmatch(r"[0-9.]+", hostname) is not None
    ):
        raise ValueError(f"{name} must contain exact hostnames only")
    return hostname


def _provider_hostname_allowlist(
    name: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    values = default if raw_value is None else tuple(
        item.strip() for item in raw_value.split(",") if item.strip()
    )
    normalized: list[str] = []
    for value in values:
        hostname = _exact_provider_hostname(value, name=name)
        if hostname not in normalized:
            normalized.append(hostname)
    return tuple(normalized)


def _provider_exact_ip_allowlist(name: str) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return ()
    addresses: list[str] = []
    for raw_address in raw_value.split(","):
        candidate = raw_address.strip()
        if not candidate or candidate != raw_address:
            raise ValueError(f"{name} must contain exact IP addresses")
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError as exc:
            raise ValueError(f"{name} must contain exact IP addresses") from exc
        canonical = str(address)
        if canonical not in addresses:
            addresses.append(canonical)
    return tuple(addresses)


def _strict_env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    if raw_value == "0":
        return False
    if raw_value == "1":
        return True
    raise ValueError(f"{name} must be 0 or 1")

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
APP_TITLE = "法采新媒体运营 Agent"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "抖音短视频带货脚本智能生成系统"

# Flask 检索后端代理
SEARCH_BACKEND_URL = os.getenv("SEARCH_BACKEND_URL", "http://127.0.0.1:5000")

# 文件上传配置
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

# Product Canvas runtime project files (database rows store relative paths only).
CANVAS_DATA_DIR = os.getenv("CANVAS_DATA_DIR", "data/canvas_projects")
CANVAS_MAX_UPLOAD_BYTES = _strict_positive_env_int("CANVAS_MAX_UPLOAD_BYTES", 12_582_912)
CANVAS_MAX_IMAGE_EDGE = _strict_positive_env_int("CANVAS_MAX_IMAGE_EDGE", 16_384)
CANVAS_MAX_IMAGE_PIXELS = _strict_positive_env_int("CANVAS_MAX_IMAGE_PIXELS", 40_000_000)
CANVAS_PREVIEW_MAX_EDGE = _strict_positive_env_int("CANVAS_PREVIEW_MAX_EDGE", 2_048)
CANVAS_PROJECT_QUOTA_BYTES = _strict_positive_env_int(
    "CANVAS_PROJECT_QUOTA_BYTES", 5_368_709_120
)
CANVAS_TOTAL_QUOTA_BYTES = _strict_positive_env_int(
    "CANVAS_TOTAL_QUOTA_BYTES", 21_474_836_480
)
CANVAS_MIN_FREE_BYTES = _strict_positive_env_int("CANVAS_MIN_FREE_BYTES", 2_147_483_648)
CANVAS_REMBG_MODEL_DIR = os.getenv("CANVAS_REMBG_MODEL_DIR", "data/models/rembg")
CANVAS_REMBG_WORKERS = _strict_positive_env_int("CANVAS_REMBG_WORKERS", 1)
CANVAS_LOCAL_OPERATION_WORKERS = _strict_positive_env_int(
    "CANVAS_LOCAL_OPERATION_WORKERS", 1
)
CANVAS_REMOTE_IMAGE_MAX_BYTES = _bounded_positive_env_int(
    "CANVAS_REMOTE_IMAGE_MAX_BYTES", 26_214_400, maximum=26_214_400
)
CANVAS_PROVIDER_SECRET_KEY = os.getenv("CANVAS_PROVIDER_SECRET_KEY", "")
CANVAS_PROVIDER_ALLOWED_HOSTS = _provider_hostname_allowlist(
    "CANVAS_PROVIDER_ALLOWED_HOSTS", ("ark.cn-beijing.volces.com",)
)
CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS = _provider_hostname_allowlist(
    "CANVAS_PROVIDER_PRIVATE_ALLOWED_HOSTS", ()
)
CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS = _provider_exact_ip_allowlist(
    "CANVAS_PROVIDER_PRIVATE_ALLOWED_IPS"
)
CANVAS_ALLOW_INSECURE_PROVIDER_HTTP = _strict_env_flag(
    "CANVAS_ALLOW_INSECURE_PROVIDER_HTTP", False
)
CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS = _bounded_positive_env_int(
    "CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS", 10, maximum=60
)
CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS = _bounded_positive_env_int(
    "CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS", 60, maximum=300
)
CANVAS_PROVIDER_MAX_JSON_BYTES = _bounded_positive_env_int(
    "CANVAS_PROVIDER_MAX_JSON_BYTES", 1_048_576, maximum=4_194_304
)
CANVAS_GENERATION_CONCURRENCY = _bounded_positive_env_int(
    "CANVAS_GENERATION_CONCURRENCY", 1, maximum=16
)
CANVAS_GENERATION_LEASE_SECONDS = _bounded_positive_env_int(
    "CANVAS_GENERATION_LEASE_SECONDS", 60, maximum=900
)

if CANVAS_PREVIEW_MAX_EDGE > CANVAS_MAX_IMAGE_EDGE:
    raise ValueError("CANVAS_PREVIEW_MAX_EDGE must not exceed CANVAS_MAX_IMAGE_EDGE")
if CANVAS_PROJECT_QUOTA_BYTES > CANVAS_TOTAL_QUOTA_BYTES:
    raise ValueError("CANVAS_PROJECT_QUOTA_BYTES must not exceed CANVAS_TOTAL_QUOTA_BYTES")
if CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS < CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS:
    raise ValueError(
        "CANVAS_PROVIDER_TOTAL_TIMEOUT_SECONDS must not be less than "
        "CANVAS_PROVIDER_CONNECT_TIMEOUT_SECONDS"
    )
if CANVAS_REMBG_WORKERS != 1:
    raise ValueError("CANVAS_REMBG_WORKERS must be 1 for deterministic single-threaded cutouts")

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
