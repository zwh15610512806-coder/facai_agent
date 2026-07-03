"""AI provider registry, interface settings, and token usage metadata."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import os
from typing import Iterable
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_V4_FLASH_MODEL,
    DEEPSEEK_V4_PRO_MODEL,
    DOUBAO_BASE_URL,
    DOUBAO_MODEL,
    GLM_BASE_URL,
    GLM_MODEL,
    MINIMAX_BASE_URL,
    MINIMAX_MODEL,
    QWEN_BASE_URL,
    QWEN_MODEL,
)
from database import SessionLocal
from models import AIInterfaceSetting, AIUsageRecord


MAX_AI_TOKENS = 128_000
DEFAULT_MAX_TOKENS = 2400
USD_TO_CNY_RATE = 6.76
PLACEHOLDER_SECRET_VALUES = {
    "your-api-key",
    "your-key",
    "your-deepseek-api-key",
    "your-deepseek-api-key-here",
    "placeholder",
    "changeme",
}
DEFAULT_AI_BASE_URL_HOSTS = (
    "api.deepseek.com",
    "dashscope.aliyuncs.com",
    "api.minimax.io",
    "open.bigmodel.cn",
)


@dataclass(frozen=True)
class ModelPricing:
    input_cny_per_million: float
    output_cny_per_million: float
    source: str


@dataclass(frozen=True)
class AIProviderDefinition:
    key: str
    label: str
    api_key_env_names: tuple[str, ...]
    base_url_env: str
    default_base_url: str
    model_env: str
    default_model_name: str
    preset_models: tuple[str, ...]
    docs_url: str
    note: str = ""

    def api_key(self) -> str:
        for name in self.api_key_env_names:
            value = os.getenv(name, "").strip()
            if is_configured_secret(value):
                return value
        return ""

    def configured_env_name(self) -> str:
        for name in self.api_key_env_names:
            if is_configured_secret(os.getenv(name, "")):
                return name
        return ""

    def base_url(self) -> str:
        return os.getenv(self.base_url_env, self.default_base_url).strip()

    def default_model(self) -> str:
        return os.getenv(self.model_env, self.default_model_name).strip() or self.default_model_name

    def configured(self) -> bool:
        return bool(self.api_key())


@dataclass(frozen=True)
class AIInterfaceDefinition:
    key: str
    label: str
    group: str
    description: str
    default_provider: str = "deepseek"
    default_model: str = ""
    default_max_tokens: int = DEFAULT_MAX_TOKENS
    implemented: bool = True


def is_configured_secret(value: str | None) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    lower = value.lower()
    if lower in PLACEHOLDER_SECRET_VALUES:
        return False
    if lower.startswith("your-") or lower.startswith("replace-"):
        return False
    return True


def unique_non_empty(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = (value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return tuple(out)


def mask_secret(value: str | None) -> str:
    value = (value or "").strip()
    if not is_configured_secret(value):
        return ""
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"


def normalize_model_name(model: str | None) -> str:
    return (model or "").strip().lower()


def pricing_for_model(provider: str, model: str | None) -> ModelPricing | None:
    provider_key = (provider or "").strip().lower()
    model_key = normalize_model_name(model)
    if (provider_key, model_key) in MODEL_PRICING_CNY:
        return MODEL_PRICING_CNY[(provider_key, model_key)]

    for (rule_provider, rule_model), pricing in MODEL_PRICING_CNY.items():
        if rule_provider == provider_key and rule_model and model_key.startswith(rule_model):
            return pricing

    return PROVIDER_FALLBACK_PRICING.get(provider_key)


def estimate_usage_cost_cny(
    provider: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    pricing = pricing_for_model(provider, model)
    if not pricing:
        return 0.0
    prompt_cost = max(0, int(prompt_tokens or 0)) * pricing.input_cny_per_million / 1_000_000
    completion_cost = max(0, int(completion_tokens or 0)) * pricing.output_cny_per_million / 1_000_000
    return prompt_cost + completion_cost


def format_cny(amount: float) -> str:
    amount = max(0.0, float(amount or 0.0))
    if amount < 0.01 and amount > 0:
        return f"¥{amount:.4f}"
    return f"¥{amount:.2f}"


def _host_from_url(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").lower()


def allowed_ai_base_url_hosts() -> set[str]:
    raw = os.getenv("AI_BASE_URL_ALLOWLIST", "").strip()
    if raw:
        return {host for host in (_host_from_url(item.strip()) for item in raw.split(",")) if host}
    configured = {
        _host_from_url(value)
        for value in (DEEPSEEK_BASE_URL, DOUBAO_BASE_URL, MINIMAX_BASE_URL, GLM_BASE_URL, QWEN_BASE_URL)
        if value
    }
    return configured | set(DEFAULT_AI_BASE_URL_HOSTS)


def validate_ai_base_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="base_url must be an absolute http:// or https:// URL")
    if parsed.hostname.lower() not in allowed_ai_base_url_hosts():
        raise HTTPException(
            status_code=422,
            detail="base_url host is not allowed; set AI_BASE_URL_ALLOWLIST to permit it",
        )


AI_PROVIDERS: dict[str, AIProviderDefinition] = {
    "deepseek": AIProviderDefinition(
        key="deepseek",
        label="DeepSeek",
        api_key_env_names=("DEEPSEEK_API_KEY",),
        base_url_env="DEEPSEEK_BASE_URL",
        default_base_url=DEEPSEEK_BASE_URL,
        model_env="DEEPSEEK_MODEL",
        default_model_name=DEEPSEEK_MODEL,
        preset_models=unique_non_empty((
            DEEPSEEK_V4_FLASH_MODEL,
            DEEPSEEK_V4_PRO_MODEL,
            "deepseek-chat",
            "deepseek-reasoner",
        )),
        docs_url="https://api-docs.deepseek.com/",
    ),
    "doubao": AIProviderDefinition(
        key="doubao",
        label="豆包 / 火山方舟",
        api_key_env_names=("ARK_API_KEY", "DOUBAO_API_KEY"),
        base_url_env="ARK_BASE_URL",
        default_base_url=DOUBAO_BASE_URL,
        model_env="ARK_MODEL",
        default_model_name=DOUBAO_MODEL,
        preset_models=unique_non_empty((DOUBAO_MODEL,)),
        docs_url="https://www.volcengine.com/docs/82379/1330626",
        note="豆包模型通常填写火山方舟 Endpoint ID；Base URL 可用 ARK_BASE_URL 或 DOUBAO_BASE_URL 配置。",
    ),
    "minimax": AIProviderDefinition(
        key="minimax",
        label="MiniMax",
        api_key_env_names=("MINIMAX_API_KEY",),
        base_url_env="MINIMAX_BASE_URL",
        default_base_url=MINIMAX_BASE_URL,
        model_env="MINIMAX_MODEL",
        default_model_name=MINIMAX_MODEL,
        preset_models=("MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.7-highspeed"),
        docs_url="https://platform.minimax.io/docs/api-reference/text-openai-api",
    ),
    "glm": AIProviderDefinition(
        key="glm",
        label="GLM / 智谱",
        api_key_env_names=("GLM_API_KEY", "ZAI_API_KEY"),
        base_url_env="GLM_BASE_URL",
        default_base_url=GLM_BASE_URL,
        model_env="GLM_MODEL",
        default_model_name=GLM_MODEL,
        preset_models=("glm-5.2",),
        docs_url="https://docs.bigmodel.cn/cn/guide/develop/openai/introduction",
    ),
    "qwen": AIProviderDefinition(
        key="qwen",
        label="Qwen / 通义千问",
        api_key_env_names=("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
        base_url_env="QWEN_BASE_URL",
        default_base_url=QWEN_BASE_URL,
        model_env="QWEN_MODEL",
        default_model_name=QWEN_MODEL,
        preset_models=("qwen-plus", "qwen-flash", "qwen-turbo", "qwen-max"),
        docs_url="https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope",
    ),
}


def usd_pricing(input_usd_per_million: float, output_usd_per_million: float, source: str) -> ModelPricing:
    return ModelPricing(
        input_cny_per_million=input_usd_per_million * USD_TO_CNY_RATE,
        output_cny_per_million=output_usd_per_million * USD_TO_CNY_RATE,
        source=source,
    )


MODEL_PRICING_CNY: dict[tuple[str, str], ModelPricing] = {
    ("deepseek", "deepseek-v4-flash"): usd_pricing(0.14, 0.28, "DeepSeek official pricing, cache-miss input"),
    ("deepseek", "deepseek-chat"): usd_pricing(0.14, 0.28, "DeepSeek official pricing, cache-miss input"),
    ("deepseek", "deepseek-reasoner"): usd_pricing(0.14, 0.28, "DeepSeek official pricing, cache-miss input"),
    ("deepseek", "deepseek-v4-pro"): usd_pricing(0.435, 0.87, "DeepSeek official pricing, cache-miss input"),
    ("doubao", "doubao-1.5-pro-32k"): ModelPricing(0.4, 2.0, "Volcengine Ark official pricing"),
    ("doubao", "doubao"): ModelPricing(0.4, 2.0, "Volcengine Ark Doubao fallback estimate"),
    ("minimax", "minimax-m3"): usd_pricing(0.30, 1.20, "MiniMax official standard pricing, <=512k input"),
    ("minimax", "minimax-m2.7"): usd_pricing(0.30, 1.20, "MiniMax official standard pricing"),
    ("minimax", "minimax-m2.7-highspeed"): usd_pricing(0.60, 2.40, "MiniMax official standard pricing"),
    ("glm", "glm-5.2"): usd_pricing(1.40, 4.40, "Z.AI official pricing"),
    ("qwen", "qwen-plus"): ModelPricing(0.8, 2.0, "Alibaba Cloud Model Studio official mainland pricing"),
    ("qwen", "qwen-flash"): ModelPricing(0.3, 0.6, "Alibaba Cloud Model Studio qwen-turbo fallback estimate"),
    ("qwen", "qwen-turbo"): ModelPricing(0.3, 0.6, "Alibaba Cloud Model Studio official mainland pricing"),
    ("qwen", "qwen-max"): ModelPricing(20.0, 60.0, "Alibaba Cloud Model Studio official mainland pricing"),
}

PROVIDER_FALLBACK_PRICING: dict[str, ModelPricing] = {
    "deepseek": MODEL_PRICING_CNY[("deepseek", "deepseek-v4-flash")],
    "doubao": MODEL_PRICING_CNY[("doubao", "doubao")],
    "minimax": MODEL_PRICING_CNY[("minimax", "minimax-m3")],
    "glm": MODEL_PRICING_CNY[("glm", "glm-5.2")],
    "qwen": MODEL_PRICING_CNY[("qwen", "qwen-plus")],
}

INSPIRATION_TOOLS_INTERFACE_KEY = "inspiration_tools"
SCRIPT_GENERATE_INTERFACE_KEY = "script_generate"
SCRIPT_CREATION_INTERFACE_KEY = "script_creation"
CONTENT_ANALYSIS_INTERFACE_KEY = "content_analysis"

INSPIRATION_TOOL_INTERFACE_KEYS: tuple[str, ...] = (
    "inspiration_thinking",
    "inspiration_research",
    "inspiration_analysis",
    "inspiration_attachment",
)
SCRIPT_CREATION_INTERFACE_KEYS: tuple[str, ...] = (
    "script_library_rewrite",
    "script_rewrite",
    "seedance_prompt",
)
CONTENT_ANALYSIS_INTERFACE_KEYS: tuple[str, ...] = (
    "product_rag_global",
    "product_rag_scoped",
    "selling_point_extract",
    "viral_script_analyze",
    "reference_script_analyze",
)


AI_INTERFACES: tuple[AIInterfaceDefinition, ...] = (
    AIInterfaceDefinition(
        key="inspiration_chat",
        label="灵感聊天",
        group="灵感",
        description="灵感页普通对话、脚本创意、选题和运营表达。",
        default_provider="doubao",
    ),
    AIInterfaceDefinition(
        key=INSPIRATION_TOOLS_INTERFACE_KEY,
        label="灵感工具模式",
        group="灵感",
        description="灵感思考模式、深入研究、数据分析和附件分析占位共用这一套模型与 API Key。",
        default_provider="doubao",
        default_max_tokens=3600,
    ),
    AIInterfaceDefinition(
        key=SCRIPT_GENERATE_INTERFACE_KEY,
        label="脚本生成",
        group="脚本",
        description="生成脚本的 AI生成引擎，默认使用豆包 / 火山方舟，也可单独配置通义、智谱、MiniMax 等模型、API Key 和 Base URL。",
        default_provider="doubao",
        default_max_tokens=3600,
    ),
    AIInterfaceDefinition(
        key=SCRIPT_CREATION_INTERFACE_KEY,
        label="脚本改写",
        group="脚本",
        description="模板库改写生成、爆款脚本改写和分镜提示词生成共用这一套模型与 API Key。",
        default_provider="doubao",
        default_max_tokens=3600,
    ),
    AIInterfaceDefinition(
        key=CONTENT_ANALYSIS_INTERFACE_KEY,
        label="资料问答与上传分析",
        group="产品/脚本库",
        description="产品问答、卖点提取、法采脚本上传分析和其他参考脚本上传分析共用这一套模型与 API Key。",
        default_model=DEEPSEEK_MODEL,
        default_max_tokens=3600,
    ),
)


INTERFACE_BY_KEY = {item.key: item for item in AI_INTERFACES}
INTERFACE_KEY_ALIASES = {
    **{key: INSPIRATION_TOOLS_INTERFACE_KEY for key in INSPIRATION_TOOL_INTERFACE_KEYS},
    **{key: SCRIPT_CREATION_INTERFACE_KEY for key in SCRIPT_CREATION_INTERFACE_KEYS},
    **{key: CONTENT_ANALYSIS_INTERFACE_KEY for key in CONTENT_ANALYSIS_INTERFACE_KEYS},
}


def canonical_interface_key(interface_key: str | None) -> str:
    key = (interface_key or "").strip()
    return INTERFACE_KEY_ALIASES.get(key, key)


def interface_usage_keys(interface_key: str | None) -> list[str]:
    canonical_key = canonical_interface_key(interface_key)
    if not canonical_key:
        return []
    keys = [canonical_key]
    keys.extend(alias for alias, target in INTERFACE_KEY_ALIASES.items() if target == canonical_key)
    return keys


def get_provider_definition(provider_key: str) -> AIProviderDefinition:
    provider = AI_PROVIDERS.get((provider_key or "").strip())
    if not provider:
        raise HTTPException(status_code=400, detail="Unsupported AI provider")
    return provider


def get_interface_definition(interface_key: str) -> AIInterfaceDefinition:
    definition = INTERFACE_BY_KEY.get(canonical_interface_key(interface_key))
    if not definition:
        raise HTTPException(status_code=404, detail="Unknown AI interface")
    return definition


def default_model_for_interface(definition: AIInterfaceDefinition) -> str:
    if definition.default_model:
        return definition.default_model
    return get_provider_definition(definition.default_provider).default_model()


ARK_DEFAULT_INTERFACE_KEYS = {
    "inspiration_chat",
    INSPIRATION_TOOLS_INTERFACE_KEY,
    SCRIPT_GENERATE_INTERFACE_KEY,
    SCRIPT_CREATION_INTERFACE_KEY,
}


def _upgrade_default_work_interface_setting(
    db: Session,
    setting: AIInterfaceSetting,
    definition: AIInterfaceDefinition,
) -> AIInterfaceSetting:
    if definition.key not in ARK_DEFAULT_INTERFACE_KEYS:
        return setting
    if (setting.provider or "").strip() != "deepseek":
        return setting
    if is_configured_secret(getattr(setting, "api_key_secret", None)):
        return setting
    if (getattr(setting, "base_url_override", None) or "").strip():
        return setting
    legacy_models = unique_non_empty((
        DEEPSEEK_MODEL,
        DEEPSEEK_V4_FLASH_MODEL,
        DEEPSEEK_V4_PRO_MODEL,
        "deepseek-chat",
        "deepseek-reasoner",
    ))
    if (setting.model or "").strip() not in legacy_models:
        return setting

    setting.provider = "doubao"
    setting.model = default_model_for_interface(definition)
    setting.max_tokens = definition.default_max_tokens
    db.commit()
    db.refresh(setting)
    return setting


def get_or_create_interface_setting(db: Session, interface_key: str) -> AIInterfaceSetting:
    definition = get_interface_definition(interface_key)
    setting = (
        db.query(AIInterfaceSetting)
        .filter(AIInterfaceSetting.interface_key == definition.key)
        .first()
    )
    if setting:
        return _upgrade_default_work_interface_setting(db, setting, definition)

    setting = AIInterfaceSetting(
        interface_key=definition.key,
        provider=definition.default_provider,
        model=default_model_for_interface(definition),
        max_tokens=definition.default_max_tokens,
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def resolve_interface_connection(setting: AIInterfaceSetting, provider: AIProviderDefinition | None = None) -> dict:
    provider_def = provider or get_provider_definition(setting.provider)
    custom_api_key = (getattr(setting, "api_key_secret", None) or "").strip()
    custom_base_url = (getattr(setting, "base_url_override", None) or "").strip()

    if is_configured_secret(custom_api_key):
        api_key = custom_api_key
        api_key_source = "interface"
        api_key_mask = mask_secret(custom_api_key)
    else:
        api_key = provider_def.api_key()
        api_key_source = "env" if api_key else "missing"
        api_key_mask = ""

    base_url = custom_base_url or provider_def.base_url()
    return {
        "api_key": api_key,
        "api_key_source": api_key_source,
        "api_key_mask": api_key_mask,
        "api_key_configured": bool(api_key),
        "base_url": base_url,
        "base_url_source": "interface" if custom_base_url else "provider",
        "custom_base_url": custom_base_url,
        "configured": bool(api_key and base_url),
    }


def update_interface_setting(
    db: Session,
    interface_key: str,
    provider: str,
    model: str,
    max_tokens: int,
    api_key: str | None = None,
    base_url: str | None = None,
    clear_api_key: bool = False,
) -> AIInterfaceSetting:
    definition = get_interface_definition(interface_key)
    provider_def = get_provider_definition(provider)
    model = (model or "").strip()
    if not model:
        model = provider_def.default_model()
    if not model:
        raise HTTPException(status_code=400, detail="Model is required")
    if max_tokens < 1 or max_tokens > MAX_AI_TOKENS:
        raise HTTPException(status_code=422, detail="max_tokens out of range")

    setting = get_or_create_interface_setting(db, definition.key)
    old_provider = setting.provider
    provider_changed = old_provider != provider_def.key

    setting.provider = provider_def.key
    setting.model = model
    setting.max_tokens = int(max_tokens)
    if api_key is not None and api_key.strip():
        setting.api_key_secret = api_key.strip()
    elif clear_api_key or provider_changed:
        setting.api_key_secret = ""

    if base_url is not None:
        base_url = base_url.strip()
        if base_url:
            validate_ai_base_url(base_url)
        setting.base_url_override = base_url
    elif provider_changed:
        setting.base_url_override = ""
    db.commit()
    db.refresh(setting)
    return setting


def provider_to_dict(provider: AIProviderDefinition) -> dict:
    return {
        "key": provider.key,
        "label": provider.label,
        "configured": provider.configured(),
        "configured_env": provider.configured_env_name(),
        "api_key_env_names": list(provider.api_key_env_names),
        "base_url_env": provider.base_url_env,
        "base_url": provider.base_url(),
        "model_env": provider.model_env,
        "default_model": provider.default_model(),
        "preset_models": list(provider.preset_models),
        "docs_url": provider.docs_url,
        "note": provider.note,
    }


def estimate_query_cost_cny(query) -> float:
    rows = (
        query.with_entities(
            AIUsageRecord.provider,
            AIUsageRecord.model,
            func.coalesce(func.sum(AIUsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsageRecord.completion_tokens), 0),
        )
        .group_by(AIUsageRecord.provider, AIUsageRecord.model)
        .all()
    )
    total = 0.0
    for provider, model, prompt_tokens, completion_tokens in rows:
        total += estimate_usage_cost_cny(provider, model, prompt_tokens, completion_tokens)
    return total


def usage_totals(db: Session, interface_key: str | None = None) -> dict:
    query = db.query(AIUsageRecord)
    if interface_key:
        query = query.filter(AIUsageRecord.interface_key.in_(interface_usage_keys(interface_key)))
    total_tokens = query.with_entities(func.coalesce(func.sum(AIUsageRecord.total_tokens), 0)).scalar() or 0
    calls = query.count()
    total_cost = estimate_query_cost_cny(query)

    today_start = datetime.combine(datetime.now().date(), time.min)
    today_query = query.filter(AIUsageRecord.created_at >= today_start)
    today_tokens = today_query.with_entities(func.coalesce(func.sum(AIUsageRecord.total_tokens), 0)).scalar() or 0
    today_calls = today_query.count()
    today_cost = estimate_query_cost_cny(today_query)
    return {
        "total_tokens": int(total_tokens or 0),
        "calls": int(calls or 0),
        "today_tokens": int(today_tokens or 0),
        "today_calls": int(today_calls or 0),
        "estimated_cost_cny": round(total_cost, 6),
        "estimated_cost_display": format_cny(total_cost),
        "today_estimated_cost_cny": round(today_cost, 6),
        "today_estimated_cost_display": format_cny(today_cost),
    }


def latest_usage(db: Session, interface_key: str) -> AIUsageRecord | None:
    return (
        db.query(AIUsageRecord)
        .filter(AIUsageRecord.interface_key.in_(interface_usage_keys(interface_key)))
        .order_by(AIUsageRecord.created_at.desc(), AIUsageRecord.id.desc())
        .first()
    )


def usage_record_to_dict(record: AIUsageRecord) -> dict:
    return {
        "id": record.id,
        "interface_key": record.interface_key,
        "provider": record.provider,
        "model": record.model,
        "prompt_tokens": record.prompt_tokens,
        "completion_tokens": record.completion_tokens,
        "total_tokens": record.total_tokens,
        "usage_source": record.usage_source,
        "latency_ms": record.latency_ms,
        "status": record.status,
        "error_summary": record.error_summary or "",
        "created_at": record.created_at.isoformat() if record.created_at else "",
    }


def display_model_for_interface(setting: AIInterfaceSetting, latest: AIUsageRecord | None) -> str:
    if not latest or not latest.model:
        return setting.model
    if latest.created_at and setting.updated_at and latest.created_at < setting.updated_at:
        return setting.model
    return latest.model


def interface_to_dict(db: Session, definition: AIInterfaceDefinition) -> dict:
    setting = get_or_create_interface_setting(db, definition.key)
    latest = latest_usage(db, definition.key)
    provider = get_provider_definition(setting.provider)
    connection = resolve_interface_connection(setting, provider)
    latest_model = latest.model if latest else ""
    display_model = display_model_for_interface(setting, latest)
    return {
        "interface_key": definition.key,
        "label": definition.label,
        "group": definition.group,
        "description": definition.description,
        "implemented": definition.implemented,
        "provider": setting.provider,
        "provider_label": provider.label,
        "provider_configured": connection["configured"],
        "model": setting.model,
        "latest_model": latest_model,
        "display_model": display_model,
        "max_tokens": setting.max_tokens,
        "api_key_configured": connection["api_key_configured"],
        "api_key_source": connection["api_key_source"],
        "api_key_mask": connection["api_key_mask"],
        "base_url": connection["base_url"],
        "base_url_source": connection["base_url_source"],
        "custom_base_url": connection["custom_base_url"],
        "usage": usage_totals(db, definition.key),
        "latest_status": latest.status if latest else "",
        "latest_called_at": latest.created_at.isoformat() if latest and latest.created_at else "",
    }


def list_interface_dicts(db: Session) -> list[dict]:
    return [interface_to_dict(db, definition) for definition in AI_INTERFACES]


def list_usage_records(db: Session, limit: int = 50, interface_key: str | None = None) -> list[dict]:
    query = db.query(AIUsageRecord)
    if interface_key:
        query = query.filter(AIUsageRecord.interface_key.in_(interface_usage_keys(interface_key)))
    records = (
        query.order_by(AIUsageRecord.created_at.desc(), AIUsageRecord.id.desc())
        .limit(max(1, min(int(limit or 50), 200)))
        .all()
    )
    return [usage_record_to_dict(record) for record in records]


def _record_with_session(db: Session, record: AIUsageRecord) -> None:
    db.add(record)
    db.commit()


def record_usage(
    *,
    interface_key: str,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    usage_source: str = "estimated",
    latency_ms: int = 0,
    status: str,
    error_summary: str = "",
    db: Session | None = None,
) -> None:
    error_summary = (error_summary or "").strip()
    if len(error_summary) > 500:
        error_summary = error_summary[:497] + "..."
    record = AIUsageRecord(
        interface_key=canonical_interface_key(interface_key),
        provider=provider,
        model=model,
        prompt_tokens=max(0, int(prompt_tokens or 0)),
        completion_tokens=max(0, int(completion_tokens or 0)),
        total_tokens=max(0, int(total_tokens or 0)),
        usage_source=usage_source,
        latency_ms=max(0, int(latency_ms or 0)),
        status=status,
        error_summary=error_summary,
    )
    if db is not None:
        _record_with_session(db, record)
        return
    session = SessionLocal()
    try:
        _record_with_session(session, record)
    finally:
        session.close()
