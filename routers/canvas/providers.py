"""Credential-safe Product Canvas Provider catalog and management routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from services.canvas.access import require_canvas_paid_access
from services.canvas.credentials import (
    ProviderCredentialConfigurationError,
    ProviderSecretCodec,
)
from services.canvas.provider_catalog import (
    ProviderCatalogConflict,
    ProviderCatalogNotFound,
    ProviderCatalogValidationError,
    create_model_profile,
    create_provider,
    disable_provider,
    list_model_catalog,
    list_provider_catalog,
    provider_test_status,
    update_model_profile,
    update_provider,
)
from services.canvas.provider_network import (
    ProviderNetworkError,
    ProviderNetworkPolicy,
    validate_provider_base_url,
)
from services.canvas.provider_schemas import (
    ModelCatalogEntry,
    ModelProfileCreate,
    ModelProfileUpdate,
    ModelProfileView,
    ProviderCatalogEntry,
    ProviderCreate,
    ProviderTestRequest,
    ProviderTestResult,
    ProviderUpdate,
    ProviderView,
)


router = APIRouter()


def _configured_codec_or_none() -> ProviderSecretCodec | None:
    try:
        return ProviderSecretCodec.from_env()
    except ProviderCredentialConfigurationError:
        return None


def _validated_provider_payload(payload: ProviderCreate | ProviderUpdate):
    base_url = payload.base_url
    if base_url is None:
        return payload
    origin = validate_provider_base_url(
        base_url,
        policy=ProviderNetworkPolicy.from_config(),
    )
    return payload.model_copy(update={"base_url": origin.url})


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderCatalogNotFound):
        return HTTPException(status_code=404, detail="Image Provider resource not found")
    if isinstance(exc, ProviderCatalogConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ProviderCatalogValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ProviderCredentialConfigurationError):
        return HTTPException(
            status_code=503,
            detail="Canvas Provider credential encryption is not configured",
        )
    if isinstance(exc, ProviderNetworkError):
        return HTTPException(status_code=422, detail="Provider base URL is not allowed")
    raise exc


@router.get("/model-providers", response_model=list[ProviderCatalogEntry])
def get_model_providers(db: Session = Depends(get_db)):
    return list_provider_catalog(db)


@router.get(
    "/model-providers/{provider_id}/models",
    response_model=list[ModelCatalogEntry],
)
def get_provider_models(provider_id: str, db: Session = Depends(get_db)):
    try:
        return list_model_catalog(db, provider_id=provider_id)
    except ProviderCatalogNotFound as exc:
        raise HTTPException(status_code=404, detail="Image Provider not found") from exc


@router.post(
    "/model-providers",
    response_model=ProviderView,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_canvas_paid_access)],
)
def post_model_provider(payload: ProviderCreate, db: Session = Depends(get_db)):
    try:
        provider = create_provider(
            db,
            request=_validated_provider_payload(payload),
            codec=_configured_codec_or_none(),
        )
        db.commit()
        return provider
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.patch(
    "/model-providers/{provider_id}",
    response_model=ProviderView,
    dependencies=[Depends(require_canvas_paid_access)],
)
def patch_model_provider(
    provider_id: str,
    payload: ProviderUpdate,
    db: Session = Depends(get_db),
):
    try:
        provider = update_provider(
            db,
            provider_id=provider_id,
            request=_validated_provider_payload(payload),
            codec=_configured_codec_or_none(),
        )
        db.commit()
        return provider
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.delete(
    "/model-providers/{provider_id}",
    response_model=ProviderView,
    dependencies=[Depends(require_canvas_paid_access)],
)
def delete_model_provider(provider_id: str, db: Session = Depends(get_db)):
    try:
        provider = disable_provider(db, provider_id=provider_id)
        db.commit()
        return provider
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post(
    "/model-providers/{provider_id}/test",
    response_model=ProviderTestResult,
    dependencies=[Depends(require_canvas_paid_access)],
)
def test_model_provider(
    provider_id: str,
    payload: ProviderTestRequest,
    db: Session = Depends(get_db),
):
    del payload  # A live paid probe is intentionally deferred until an adapter supports it.
    try:
        result = provider_test_status(
            db,
            provider_id=provider_id,
            codec=_configured_codec_or_none(),
        )
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post(
    "/model-providers/{provider_id}/models",
    response_model=ModelProfileView,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_canvas_paid_access)],
)
def post_model_profile(
    provider_id: str,
    payload: ModelProfileCreate,
    db: Session = Depends(get_db),
):
    try:
        model = create_model_profile(db, provider_id=provider_id, request=payload)
        db.commit()
        return model
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.patch(
    "/models/{model_profile_id}",
    response_model=ModelProfileView,
    dependencies=[Depends(require_canvas_paid_access)],
)
def patch_model_profile(
    model_profile_id: str,
    payload: ModelProfileUpdate,
    db: Session = Depends(get_db),
):
    try:
        model = update_model_profile(db, model_profile_id=model_profile_id, request=payload)
        db.commit()
        return model
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


__all__ = ["router"]
