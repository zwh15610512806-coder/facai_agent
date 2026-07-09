"""AI configuration and token usage APIs."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from services.ai_config import (
    AI_PROVIDERS,
    MAX_AI_TOKENS,
    get_interface_definition,
    interface_to_dict,
    list_interface_dicts,
    list_usage_records,
    provider_to_dict,
    update_interface_setting,
    usage_totals,
)
from vector_store import embedding_health_check


router = APIRouter()


class AIInterfaceUpdate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=120)
    max_tokens: int = Field(..., ge=1, le=MAX_AI_TOKENS)
    api_key: str | None = Field(None, max_length=5000)
    base_url: str | None = Field(None, max_length=500)
    clear_api_key: bool = False


class VectorHealthResponse(BaseModel):
    provider: str = ""
    base_url: str = ""
    model: str = ""
    configured: bool = False
    healthy: bool = False
    dimension: int | None = None
    error: str = ""


@router.get("/providers")
def list_ai_providers():
    return {
        "providers": [provider_to_dict(provider) for provider in AI_PROVIDERS.values()],
    }


@router.get("/interfaces")
def list_ai_interfaces(db: Session = Depends(get_db)):
    return {"interfaces": list_interface_dicts(db)}


@router.get("/vector-health", response_model=VectorHealthResponse)
def get_vector_health():
    return embedding_health_check()


@router.put("/interfaces/{interface_key}")
def update_ai_interface(
    interface_key: str,
    data: AIInterfaceUpdate,
    db: Session = Depends(get_db),
):
    setting = update_interface_setting(
        db=db,
        interface_key=interface_key,
        provider=data.provider,
        model=data.model,
        max_tokens=data.max_tokens,
        api_key=data.api_key,
        base_url=data.base_url,
        clear_api_key=data.clear_api_key,
    )
    definition = get_interface_definition(setting.interface_key)
    return interface_to_dict(db, definition)


@router.get("/usage")
def list_ai_usage(
    interface_key: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return {
        "totals": usage_totals(db, interface_key),
        "records": list_usage_records(db, limit=limit, interface_key=interface_key),
    }
