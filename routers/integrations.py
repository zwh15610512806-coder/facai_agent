"""Dedicated session boundary for integration-center administration."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from commerce_models import CommerceProduct, CommerceProductLink
from integration_models import (
    IntegrationAppConfig,
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationSyncCheckpoint,
    IntegrationSyncRun,
)
from integrations.actor import (
    IntegrationActor,
    current_integration_actor,
    integration_actor_digest,
)
from integrations.app_configs import (
    list_provider_app_configs,
    upsert_provider_app_config,
)
from integrations.audit import write_security_audit
from integrations.connections import persist_oauth_result
from integrations.connectors.registry import (
    ConnectorUnavailable,
    connector_registry,
)
from integrations.oauth import (
    OAuthStateInvalid,
    consume_oauth_state,
    create_oauth_state,
    validate_return_path,
)
from integrations.exports import (
    ExportRequestConflict,
    create_export_job,
    export_job_view,
    get_export_job,
    resolve_export_path,
)
from integrations.management import (
    get_authorization_view,
    get_connection_view,
    list_connection_views,
    enqueue_manual_sync,
    ManagementConflict,
)
from integrations.reporting import (
    ReportingRange,
    SHANGHAI,
    list_ad_entities,
    list_ad_metrics,
    list_orders,
    list_products,
    list_refunds,
    list_sync_runs,
    overview,
    sync_run_view,
)
from integrations.schemas import (
    AdEntityDataQuery,
    AdMetricDataQuery,
    AppConfigUpdate,
    AppConfigView,
    AuthorizationStartRequest,
    AuthorizationStartResponse,
    CommonDataQuery,
    ExportCreateRequest,
    ManualSyncRequest,
    OrderDataQuery,
    ProductDataQuery,
    ProductLinkUpdate,
    PurgeConnectionRequest,
    ReauthorizationRequest,
    RetryRunRequest,
    SyncRunDataQuery,
    ProviderListResponse,
    RefundDataQuery,
)
from integrations.settings import MASTER_KEY_ENV, load_integration_settings
from integrations.sync.queue import enqueue_job
from integrations.types import (
    AuthorizationStatus,
    CheckpointStatus,
    ConnectionStatus,
    ExportStatus,
    JobStatus,
    JobType,
    Provider,
    SyncSource,
    SyncStatus,
    utc_now,
)
from models import JobRun, Product
from services.background_jobs import browser_owner_key
from services.security import request_actor_digest


class _SanitizedValidationRoute(APIRoute):
    """Keep integration credentials out of FastAPI's default 422 echo."""

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def sanitized_handler(request: Request):
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                audit_context = getattr(
                    request.state,
                    "integration_mutation_audit",
                    None,
                )
                if isinstance(audit_context, tuple) and len(audit_context) == 4:
                    claims, operation, target, bind = audit_context
                    with Session(bind=bind) as audit_db:
                        _commit_mutation_rejection(
                            audit_db,
                            claims=claims,
                            operation=operation,
                            target_id=target,
                            reason="validation_rejected",
                        )
                errors = [
                    {
                        "type": error.get("type", "validation_error"),
                        "loc": list(error.get("loc", ())),
                        "msg": error.get("msg", "Request validation failed"),
                    }
                    for error in exc.errors()
                ]
                return JSONResponse({"detail": errors}, status_code=422)

        return sanitized_handler


_VALIDATION_INTEGER_PATHS = frozenset(
    {
        "authorization_id",
        "commerce_product_id",
        "connection_id",
        "run_id",
    }
)


def _safe_validation_target(path_key: str | None, raw_target: object) -> str:
    if path_key is None:
        return "0"
    selected = str(raw_target)
    if path_key == "provider":
        try:
            return Provider(selected).value
        except ValueError:
            return "unknown"
    if path_key in _VALIDATION_INTEGER_PATHS:
        if re.fullmatch(r"[1-9][0-9]{0,9}", selected) is None:
            return "unknown"
        value = int(selected)
        return selected if value <= 2_147_483_647 else "unknown"
    return "unknown"


def _audit_mutation_validation(operation: str, path_key: str | None = None):
    async def dependency(
        request: Request,
        db: Session = Depends(get_db),
        claims: IntegrationActor = Depends(current_integration_actor),
    ) -> None:
        raw_target = request.path_params.get(path_key) if path_key else 0
        target = _safe_validation_target(path_key, raw_target)
        request.state.integration_mutation_audit = (
            claims,
            operation,
            target,
            db.get_bind(),
        )

    return dependency


public_router = APIRouter(
    prefix="/integrations",
    tags=["integrations-public"],
    route_class=_SanitizedValidationRoute,
)
admin_router = APIRouter(
    prefix="/api/integrations",
    tags=["integrations"],
    route_class=_SanitizedValidationRoute,
    dependencies=[Depends(current_integration_actor)],
)
operations_router = APIRouter(
    prefix="/api/operations",
    tags=["operations"],
    route_class=_SanitizedValidationRoute,
)


_PROVIDER_LABELS = {
    Provider.QIANCHUAN: "巨量千川",
    Provider.DOUDIAN: "抖店",
    Provider.TAOBAO: "淘宝店",
    Provider.PDD: "拼多多店",
}


def _credential_settings_or_503():
    settings = load_integration_settings()
    if settings.credential_ready and settings.master_key is not None:
        return settings
    missing_keys = list(settings.errors)
    if settings.master_key is None and MASTER_KEY_ENV not in missing_keys:
        missing_keys.append(MASTER_KEY_ENV)
    raise HTTPException(
        status_code=503,
        detail={
            "code": "security_configuration_incomplete",
            "missing_environment_keys": missing_keys,
        },
    )


def _provider_app_is_configured(db: Session, provider: Provider) -> bool:
    return (
        db.execute(
            select(IntegrationAppConfig.id).where(
                IntegrationAppConfig.provider == provider,
                IntegrationAppConfig.status == "configured",
                IntegrationAppConfig.app_secret_ciphertext.is_not(None),
            )
        ).scalar_one_or_none()
        is not None
    )


def _validated_authorization_url(value: object, *, expected_state: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 4096
        or "\\" in value
        or any(ord(character) <= 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError("Connector authorization URL is invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("Connector authorization URL is invalid") from None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
        or parse_qs(parsed.query, keep_blank_values=True).get("state")
        != [expected_state]
    ):
        raise ValueError("Connector authorization URL is invalid")
    return value


def _oauth_redirect(
    *,
    internal_origin: str,
    return_path: str,
    provider: Provider,
    result: str,
) -> str:
    safe_path = validate_return_path(return_path)
    query = urlencode(
        (("provider", provider.value), ("oauth_result", result)),
        doseq=False,
    )
    return f"{internal_origin}{safe_path}?{query}"


def _write_oauth_audit(
    db: Session,
    *,
    provider: Provider,
    session_digest: str,
    success: bool,
    stage: str | None = None,
) -> None:
    if success:
        write_security_audit(
            db,
            event_type="oauth_callback_succeeded",
            outcome="success",
            summary_code="oauth_completed",
            session_digest=session_digest,
            provider=provider,
            target_type="oauth",
            target_id=provider.value,
            details={},
        )
    else:
        write_security_audit(
            db,
            event_type="oauth_callback_failed",
            outcome="failure",
            summary_code="oauth_completion_failed",
            session_digest=session_digest,
            provider=provider,
            target_type="oauth",
            target_id=provider.value,
            details={"stage": stage},
        )


def _invalid_oauth_callback() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "invalid_oauth_callback"},
    )


@admin_router.get("/providers", response_model=ProviderListResponse)
def get_integration_providers(db: Session = Depends(get_db)):
    _credential_settings_or_503()
    return list_provider_app_configs(db)


@admin_router.put(
    "/providers/{provider}/app-config",
    response_model=AppConfigView,
)
def put_integration_provider_app_config(
    provider: Provider,
    payload: AppConfigUpdate,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("update_app_config", "provider")
    ),
):
    settings = _credential_settings_or_503()
    try:
        view = upsert_provider_app_config(
            db,
            provider=provider,
            update=payload,
            master_key=settings.master_key,
        session_digest=integration_actor_digest(claims),
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={"code": "app_config_persistence_failed"},
        ) from None
    return view


@admin_router.post(
    "/providers/{provider}/authorize",
    response_model=AuthorizationStartResponse,
)
def start_provider_authorization(
    provider: Provider,
    payload: AuthorizationStartRequest,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("start_authorization", "provider")
    ),
):
    session_digest = integration_actor_digest(claims)

    def reject(reason: str) -> None:
        db.rollback()
        write_security_audit(
            db,
            event_type="authorization_start_rejected",
            outcome="failure",
            summary_code="authorization_start_rejected",
            session_digest=session_digest,
            provider=provider,
            target_type="authorization_start",
            target_id=provider.value,
            details={"reason": reason},
        )
        db.commit()

    try:
        settings = _credential_settings_or_503()
    except HTTPException:
        reject("security_configuration_incomplete")
        raise
    try:
        return_path = validate_return_path(payload.return_path)
    except ValueError:
        reject("invalid_return_path")
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_return_path"},
        ) from None
    if not _provider_app_is_configured(db, provider):
        reject("provider_app_not_configured")
        raise HTTPException(
            status_code=409,
            detail={"code": "provider_app_not_configured"},
        )
    try:
        connector = connector_registry.get(provider)
    except ConnectorUnavailable:
        reject("connector_unavailable")
        raise HTTPException(
            status_code=503,
            detail={"code": "connector_unavailable"},
        ) from None

    redirect_uri = (
        f"{settings.public_base_url}/integrations/oauth/callback/{provider.value}"
    )
    try:
        raw_state = create_oauth_state(
            db,
            provider=provider,
            session_id=claims.sid,
            return_path=return_path,
        )
        authorization_url = _validated_authorization_url(
            connector.authorization_url(
                state=raw_state,
                redirect_uri=redirect_uri,
            ),
            expected_state=raw_state,
        )
        write_security_audit(
            db,
            event_type="authorization_start_succeeded",
            outcome="success",
            summary_code="authorization_start_succeeded",
            session_digest=session_digest,
            provider=provider,
            target_type="authorization_start",
            target_id=provider.value,
            details={},
        )
        db.commit()
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        reject("connector_authorization_unavailable")
        raise HTTPException(
            status_code=503,
            detail={"code": "connector_authorization_unavailable"},
        ) from None
    return AuthorizationStartResponse(authorization_url=authorization_url)


@public_router.get("/oauth/callback/{provider}")
async def complete_provider_authorization(
    provider: Provider,
    request: Request,
    db: Session = Depends(get_db),
):
    settings = load_integration_settings()
    if (
        not settings.credential_ready
        or settings.master_key is None
        or settings.internal_base_url is None
        or settings.public_base_url is None
    ):
        raise HTTPException(
            status_code=503,
            detail={"code": "security_configuration_incomplete"},
        )
    state_values = request.query_params.getlist("state")
    if (
        len(state_values) != 1
        or not state_values[0]
        or len(state_values[0]) > 256
    ):
        raise _invalid_oauth_callback()
    try:
        consumed = consume_oauth_state(
            db,
            raw_state=state_values[0],
            provider=provider,
        )
        return_path = consumed.return_path
        session_digest = consumed.initiating_session_digest
        db.commit()
    except OAuthStateInvalid:
        db.rollback()
        raise _invalid_oauth_callback() from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={"code": "oauth_state_persistence_failed"},
        ) from None

    redirect_uri = (
        f"{settings.public_base_url}/integrations/oauth/callback/{provider.value}"
    )
    code_values = request.query_params.getlist("code")
    stage = "callback_input"
    try:
        if (
            len(code_values) != 1
            or not code_values[0]
            or len(code_values[0]) > 4096
        ):
            raise ValueError("Callback code is invalid")
        stage = "connector_lookup"
        connector = connector_registry.get(provider)
        stage = "exchange"
        tokens = await connector.exchange_code(
            code=code_values[0],
            redirect_uri=redirect_uri,
        )
        stage = "discovery"
        accounts = await connector.discover_accounts(tokens)
        stage = "persistence"
        persist_oauth_result(
            db,
            provider=provider,
            tokens=tokens,
            accounts=accounts,
            master_key=settings.master_key,
        )
        _write_oauth_audit(
            db,
            provider=provider,
            session_digest=session_digest,
            success=True,
        )
        db.commit()
        result = "success"
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        db.rollback()
        try:
            _write_oauth_audit(
                db,
                provider=provider,
                session_digest=session_digest,
                success=False,
                stage=stage,
            )
            db.commit()
        except Exception as audit_exc:
            if isinstance(audit_exc, (KeyboardInterrupt, SystemExit)):
                raise
            db.rollback()
        result = "exchange_failed"
    location = _oauth_redirect(
        internal_origin=settings.internal_base_url,
        return_path=return_path,
        provider=provider,
        result=result,
    )
    return RedirectResponse(location, status_code=303)


async def _receive_provider_event(provider: Provider, request: Request):
    try:
        handler = connector_registry.get_event(provider)
    except ConnectorUnavailable:
        raise HTTPException(
            status_code=503,
            detail={"code": "event_handler_unavailable"},
        ) from None
    try:
        verified = handler.verify_event(dict(request.headers), await request.body())
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_event_signature"},
        ) from None
    del verified
    raise HTTPException(
        status_code=503,
        detail={"code": "event_pipeline_unavailable"},
    )


@public_router.get("/events/{provider}")
async def receive_provider_event_get(provider: Provider, request: Request):
    return await _receive_provider_event(provider, request)


@public_router.post("/events/{provider}")
async def receive_provider_event_post(provider: Provider, request: Request):
    return await _receive_provider_event(provider, request)


def _reporting_range(query: CommonDataQuery) -> ReportingRange:
    try:
        return ReportingRange.from_dates(
            date_from=query.date_from,
            date_to=query.date_to,
            today=datetime.now(SHANGHAI).date(),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_reporting_range"},
        ) from exc


def _commit_mutation_rejection(
    db: Session,
    *,
    claims: IntegrationActor,
    operation: str,
    target_id: int,
    reason: str,
    provider: Provider | None = None,
) -> None:
    """Persist one closed failure audit after discarding partial mutations."""

    db.rollback()
    write_security_audit(
        db,
        event_type="integration_mutation_rejected",
        outcome="failure",
        summary_code="integration_mutation_rejected",
        session_digest=integration_actor_digest(claims),
        provider=provider,
        target_type="integration_command",
        target_id=f"{operation}:{target_id}",
        details={"operation": operation, "reason": reason},
    )
    db.commit()


@operations_router.get("/overview")
def get_integration_overview(
    query: Annotated[CommonDataQuery, Query()],
    db: Session = Depends(get_db),
):
    return overview(
        db,
        reporting_range=_reporting_range(query),
        provider=query.provider,
        connection_id=query.connection_id,
    )


@operations_router.get("/filter-options")
def get_operation_filter_options(db: Session = Depends(get_db)):
    rows = db.execute(
        select(
            IntegrationConnection.id,
            IntegrationConnection.provider,
            IntegrationConnection.display_name,
            IntegrationConnection.status,
        ).order_by(IntegrationConnection.provider, IntegrationConnection.display_name)
    ).all()
    return {
        "providers": [
            {"key": provider.value, "name": _PROVIDER_LABELS[provider]}
            for provider in Provider
        ],
        "connections": [
            {
                "id": row.id,
                "provider": (
                    row.provider.value
                    if isinstance(row.provider, Provider)
                    else str(row.provider)
                ),
                "name": row.display_name,
                "status": (
                    row.status.value
                    if isinstance(row.status, ConnectionStatus)
                    else str(row.status)
                ),
            }
            for row in rows
        ],
    }


@operations_router.post("/exports", status_code=202)
def create_operation_export(
    request: Request,
    payload: ExportCreateRequest,
    db: Session = Depends(get_db),
):
    actor_digest = request_actor_digest(request)
    try:
        export_job = create_export_job(
            db,
            requester_session_digest=actor_digest,
            request=payload,
            now=utc_now(),
        )
    except ExportRequestConflict:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "connection_not_exportable"},
        ) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={"code": "export_persistence_failed"},
        ) from None
    db.commit()
    return _operation_export_job_view(export_job, now=utc_now())


def _operation_export_job_view(export_job, *, now):
    view = export_job_view(export_job, now=now)
    if view.get("download_url"):
        view["download_url"] = (
            f"/api/operations/exports/{export_job.public_id}/download"
        )
    return view


def _owned_operation_export(
    db: Session,
    public_id: str,
    request: Request,
):
    try:
        export_job = get_export_job(db, public_id)
    except ValueError:
        export_job = None
    if (
        export_job is None
        or export_job.requester_session_digest != request_actor_digest(request)
    ):
        raise HTTPException(status_code=404, detail={"code": "export_not_found"})
    return export_job


@operations_router.get("/exports/{public_id}")
def get_operation_export(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    return _operation_export_job_view(
        _owned_operation_export(db, public_id, request),
        now=utc_now(),
    )


@operations_router.get("/exports/{public_id}/download")
def download_operation_export(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    export_job = _owned_operation_export(db, public_id, request)
    now = utc_now()
    if export_job.expires_at <= now:
        raise HTTPException(status_code=410, detail={"code": "export_expired"})
    if export_job.status is not ExportStatus.READY or not export_job.relative_file_path:
        raise HTTPException(status_code=409, detail={"code": "export_not_ready"})
    settings = _credential_settings_or_503()
    try:
        path = resolve_export_path(
            archive_dir=settings.archive_dir,
            relative_path=export_job.relative_file_path,
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={"code": "export_file_missing"},
        ) from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "export_file_missing"})
    media_type = (
        "text/csv; charset=utf-8"
        if export_job.format == "csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"integration-{export_job.public_id}.{export_job.format}",
        headers={"Cache-Control": "no-store"},
    )


@operations_router.put("/products/{commerce_product_id}/link")
def put_operation_product_link(
    commerce_product_id: int,
    payload: ProductLinkUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    if commerce_product_id <= 0:
        raise HTTPException(status_code=404, detail={"code": "product_not_found"})
    commerce_product = db.scalar(
        select(CommerceProduct)
        .where(CommerceProduct.id == commerce_product_id)
        .with_for_update()
    )
    internal_product = db.scalar(
        select(Product).where(Product.id == payload.product_id)
    )
    if commerce_product is None or internal_product is None:
        db.rollback()
        raise HTTPException(status_code=404, detail={"code": "product_not_found"})
    actor_digest = request_actor_digest(request)
    now = datetime.now(timezone.utc)
    db.execute(
        postgres_insert(CommerceProductLink)
        .values(
            commerce_product_id=commerce_product.id,
            product_id=internal_product.id,
            linked_by_session_digest=actor_digest,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_commerce_product_links_commerce_product",
            set_={
                "product_id": internal_product.id,
                "linked_by_session_digest": actor_digest,
                "updated_at": now,
            },
        )
    )
    db.commit()
    return {
        "commerce_product_id": commerce_product.id,
        "product_id": internal_product.id,
        "linked": True,
    }


@operations_router.delete("/products/{commerce_product_id}/link")
def delete_operation_product_link(
    commerce_product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    commerce_product = db.scalar(
        select(CommerceProduct).where(CommerceProduct.id == commerce_product_id)
    )
    if commerce_product is None:
        db.rollback()
        raise HTTPException(status_code=404, detail={"code": "product_not_found"})
    db.execute(
        delete(CommerceProductLink).where(
            CommerceProductLink.commerce_product_id == commerce_product_id
        )
    )
    db.commit()
    return {"commerce_product_id": commerce_product.id, "linked": False}


@admin_router.get("/connections")
def get_integration_connections(db: Session = Depends(get_db)):
    return {"connections": list_connection_views(db)}


@admin_router.get("/connections/{connection_id}")
def get_integration_connection(
    connection_id: int,
    db: Session = Depends(get_db),
):
    selected = get_connection_view(db, connection_id)
    if selected is None:
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
    return selected


@admin_router.get("/authorizations/{authorization_id}")
def get_integration_authorization(
    authorization_id: int,
    db: Session = Depends(get_db),
):
    selected = get_authorization_view(db, authorization_id)
    if selected is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "authorization_not_found"},
        )
    return selected


@admin_router.post("/connections/{connection_id}/sync", status_code=202)
def start_manual_integration_sync(
    connection_id: int,
    payload: ManualSyncRequest,
    request: Request,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    x_facai_client_id: str | None = Header(None, alias="X-Facai-Client-Id"),
    _validation_audit: None = Depends(
        _audit_mutation_validation("manual_sync", "connection_id")
    ),
):
    session_digest = integration_actor_digest(claims)
    try:
        result, units, connection = enqueue_manual_sync(
            db,
            connection_id=connection_id,
            request=payload,
            now=utc_now(),
        )
    except LookupError:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="manual_sync",
            target_id=connection_id,
            reason="connection_not_found",
        )
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found"},
        ) from None
    except ManagementConflict:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="manual_sync",
            target_id=connection_id,
            reason="sync_not_available",
        )
        raise HTTPException(
            status_code=409,
            detail={"code": "sync_not_available"},
        ) from None
    write_security_audit(
        db,
        event_type="manual_sync_enqueued",
        outcome="success",
        summary_code="manual_sync_enqueued",
        session_digest=session_digest,
        provider=connection.provider,
        target_type="connection",
        target_id=str(connection.id),
        details={
            "resource_count": len(payload.resources),
            "unit_count": len(units),
        },
    )
    if x_facai_client_id:
        try:
            normalized_client_id = str(uuid.UUID(x_facai_client_id))
        except (ValueError, AttributeError) as exc:
            raise HTTPException(status_code=400, detail="X-Facai-Client-Id 必须是 UUID") from exc
        request_id = str(payload.request_id)
        db.add(JobRun(
            public_id=str(uuid.uuid4()),
            owner_key=browser_owner_key(request_actor_digest(request), normalized_client_id),
            job_type="integration.adapter.sync",
            queue_group="maintenance",
            origin_path="/app/api-connections",
            source_ref=f"integration-sync:{request_id}",
            idempotency_key=request_id,
            status="pending",
            message="集成同步等待执行",
            request_payload={
                "connection_id": connection.id,
                "resources": [item.value for item in payload.resources],
                "date_from": payload.date_from.isoformat(),
                "date_to": payload.date_to.isoformat(),
            },
            partial_result={},
            result_payload={},
            details={},
            progress_current=0,
            progress_total=result.sync_units,
            version=1,
            attempt_count=0,
            max_attempts=6,
            created_at=utc_now().replace(tzinfo=None),
        ))
    db.commit()
    return {
        "connection_id": connection.id,
        "sync_units": result.sync_units,
        "request_id": str(payload.request_id),
    }


@admin_router.post("/connections/{connection_id}/reauthorize")
def reauthorize_integration_connection(
    connection_id: int,
    payload: ReauthorizationRequest,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("reauthorize", "connection_id")
    ),
):
    connection = db.scalar(
        select(IntegrationConnection).where(IntegrationConnection.id == connection_id)
    )
    if connection is None:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="reauthorize",
            target_id=connection_id,
            reason="connection_not_found",
        )
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
    return start_provider_authorization(
        connection.provider,
        AuthorizationStartRequest(return_path=payload.return_path),
        db,
        claims,
    )


@admin_router.delete("/connections/{connection_id}")
def disable_integration_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("disable_connection", "connection_id")
    ),
):
    connection = db.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.id == connection_id)
        .with_for_update()
    )
    if connection is None:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="disable_connection",
            target_id=connection_id,
            reason="connection_not_found",
        )
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
    now = utc_now()
    connection.status = ConnectionStatus.DISABLED
    connection.disabled_at = connection.disabled_at or now
    connection.updated_at = now
    write_security_audit(
        db,
        event_type="connection_disabled",
        outcome="success",
        summary_code="connection_disabled",
        session_digest=integration_actor_digest(claims),
        provider=connection.provider,
        target_type="connection",
        target_id=str(connection.id),
        details={},
    )
    db.commit()
    return {"connection_id": connection.id, "status": ConnectionStatus.DISABLED.value}


@admin_router.delete("/authorizations/{authorization_id}")
def disable_integration_authorization(
    authorization_id: int,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("disable_authorization", "authorization_id")
    ),
):
    authorization = db.scalar(
        select(IntegrationAuthorization)
        .where(IntegrationAuthorization.id == authorization_id)
        .with_for_update()
    )
    if authorization is None:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="disable_authorization",
            target_id=authorization_id,
            reason="authorization_not_found",
        )
        raise HTTPException(
            status_code=404,
            detail={"code": "authorization_not_found"},
        )
    now = utc_now()
    authorization.access_token_ciphertext = ""
    authorization.access_token_tail = ""
    authorization.refresh_token_ciphertext = None
    authorization.refresh_token_tail = None
    authorization.access_expires_at = None
    authorization.refresh_expires_at = None
    authorization.status = AuthorizationStatus.DISABLED
    authorization.updated_at = now
    children = db.scalars(
        select(IntegrationConnection)
        .where(IntegrationConnection.authorization_id == authorization.id)
        .with_for_update()
    ).all()
    for connection in children:
        connection.status = ConnectionStatus.DISABLED
        connection.disabled_at = connection.disabled_at or now
        connection.updated_at = now
    write_security_audit(
        db,
        event_type="authorization_disabled",
        outcome="success",
        summary_code="authorization_disabled_locally",
        session_digest=integration_actor_digest(claims),
        provider=authorization.provider,
        target_type="authorization",
        target_id=str(authorization.id),
        details={"child_connection_count": len(children), "platform_revoke": "unavailable"},
    )
    db.commit()
    return {
        "authorization_id": authorization.id,
        "status": AuthorizationStatus.DISABLED.value,
        "disabled_connections": len(children),
    }


@admin_router.post("/connections/{connection_id}/purge", status_code=202)
def purge_integration_connection(
    connection_id: int,
    payload: PurgeConnectionRequest,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("purge_connection", "connection_id")
    ),
):
    connection = db.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.id == connection_id)
        .with_for_update()
    )
    if connection is None:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="purge_connection",
            target_id=connection_id,
            reason="connection_not_found",
        )
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
    if payload.confirmation != connection.display_name:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="purge_connection",
            target_id=connection_id,
            reason="confirmation_mismatch",
            provider=connection.provider,
        )
        raise HTTPException(status_code=422, detail={"code": "confirmation_mismatch"})
    now = utc_now()
    connection.status = ConnectionStatus.DISABLED
    connection.disabled_at = connection.disabled_at or now
    connection.updated_at = now
    job = enqueue_job(
        db,
        job_type=JobType.PURGE_CONNECTION,
        target_id=connection.id,
        logical_request={"namespace": "connection_purge"},
        payload={"connection_id": connection.id},
        priority=200,
    )
    if job.status in {
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.SUCCEEDED,
    }:
        job.status = JobStatus.QUEUED
        job.available_at = now
        job.attempts = 0
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.last_error_code = None
        job.last_error_summary = None
        job.completed_at = None
        job.updated_at = now
    write_security_audit(
        db,
        event_type="connection_purge_enqueued",
        outcome="success",
        summary_code="connection_purge_enqueued",
        session_digest=integration_actor_digest(claims),
        provider=connection.provider,
        target_type="connection",
        target_id=str(connection.id),
        details={"job_id": job.id},
    )
    db.commit()
    return {
        "connection_id": connection.id,
        "job_id": job.id,
        "status": job.status.value,
    }


@admin_router.post("/sync-runs/{run_id}/retry", status_code=202)
def retry_integration_sync_run(
    run_id: int,
    payload: RetryRunRequest,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("retry_sync_run", "run_id")
    ),
):
    row = db.execute(
        select(IntegrationSyncRun, IntegrationSyncCheckpoint, IntegrationConnection)
        .join(
            IntegrationSyncCheckpoint,
            IntegrationSyncCheckpoint.id == IntegrationSyncRun.checkpoint_id,
        )
        .join(
            IntegrationConnection,
            IntegrationConnection.id == IntegrationSyncCheckpoint.connection_id,
        )
        .where(IntegrationSyncRun.id == run_id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="retry_sync_run",
            target_id=run_id,
            reason="sync_run_not_found",
        )
        raise HTTPException(status_code=404, detail={"code": "sync_run_not_found"})
    parent, checkpoint, connection = row
    if parent.status not in {SyncStatus.FAILED, SyncStatus.PARTIAL_SUCCESS}:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="retry_sync_run",
            target_id=run_id,
            reason="sync_run_not_retryable",
            provider=connection.provider,
        )
        raise HTTPException(status_code=409, detail={"code": "sync_run_not_retryable"})
    now = utc_now()
    child = IntegrationSyncRun(
        checkpoint_id=checkpoint.id,
        parent_run_id=parent.id,
        source=SyncSource.RETRY,
        status=SyncStatus.QUEUED,
        resource_type=parent.resource_type,
        window_start=parent.window_start,
        window_end=parent.window_end,
        progress=0,
        records_read=0,
        records_written=0,
        records_skipped=0,
        records_quarantined=0,
        created_at=now,
    )
    db.add(child)
    checkpoint.status = CheckpointStatus.PENDING
    checkpoint.next_retry_at = None
    checkpoint.lease_owner = None
    checkpoint.lease_expires_at = None
    checkpoint.heartbeat_at = None
    checkpoint.updated_at = now
    db.flush((child, checkpoint))
    job = enqueue_job(
        db,
        job_type=JobType.SYNC_RESOURCE,
        target_id=connection.id,
        logical_request={"parent_run_id": parent.id},
        logical_request_id=str(payload.request_id),
        manual=True,
        payload={
            "connection_id": connection.id,
            "resource_type": parent.resource_type.value,
            "window_start": parent.window_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "window_end": parent.window_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "checkpoint_id": checkpoint.id,
        },
    )
    write_security_audit(
        db,
        event_type="sync_run_retry_enqueued",
        outcome="success",
        summary_code="sync_run_retry_enqueued",
        session_digest=integration_actor_digest(claims),
        provider=connection.provider,
        target_type="sync_run",
        target_id=str(parent.id),
        details={"child_run_id": child.id, "job_id": job.id},
    )
    db.commit()
    return {"run_id": child.id, "parent_run_id": parent.id, "job_id": job.id}


@operations_router.get("/orders")
def get_integration_orders(
    query: Annotated[OrderDataQuery, Query()],
    db: Session = Depends(get_db),
):
    return list_orders(
        db,
        reporting_range=_reporting_range(query),
        provider=query.provider,
        connection_id=query.connection_id,
        status=query.status,
        search=query.search,
        page=query.page,
        per_page=query.per_page,
    ).as_dict()


@operations_router.get("/products")
def get_integration_products(
    query: Annotated[ProductDataQuery, Query()],
    db: Session = Depends(get_db),
):
    return list_products(
        db,
        reporting_range=_reporting_range(query),
        provider=query.provider,
        connection_id=query.connection_id,
        status=query.status,
        search=query.search,
        link_status=query.link_status,
        page=query.page,
        per_page=query.per_page,
    ).as_dict()


@operations_router.get("/refunds")
def get_integration_refunds(
    query: Annotated[RefundDataQuery, Query()],
    db: Session = Depends(get_db),
):
    return list_refunds(
        db,
        reporting_range=_reporting_range(query),
        provider=query.provider,
        connection_id=query.connection_id,
        status=query.status,
        search=query.search,
        page=query.page,
        per_page=query.per_page,
    ).as_dict()


@operations_router.get("/ad-entities")
def get_integration_ad_entities(
    query: Annotated[AdEntityDataQuery, Query()],
    db: Session = Depends(get_db),
):
    return list_ad_entities(
        db,
        reporting_range=_reporting_range(query),
        provider=query.provider,
        connection_id=query.connection_id,
        entity_type=query.entity_type,
        search=query.search,
        page=query.page,
        per_page=query.per_page,
    ).as_dict()


@operations_router.get("/ad-metrics")
def get_integration_ad_metrics(
    query: Annotated[AdMetricDataQuery, Query()],
    db: Session = Depends(get_db),
):
    return list_ad_metrics(
        db,
        reporting_range=_reporting_range(query),
        provider=query.provider,
        connection_id=query.connection_id,
        entity_type=query.entity_type,
        granularity=query.granularity,
        page=query.page,
        per_page=query.per_page,
    ).as_dict()


@admin_router.get("/sync-runs")
@operations_router.get("/sync-runs")
def get_integration_sync_runs(
    query: Annotated[SyncRunDataQuery, Query()],
    db: Session = Depends(get_db),
):
    return list_sync_runs(
        db,
        reporting_range=_reporting_range(query),
        provider=query.provider,
        connection_id=query.connection_id,
        status=query.status,
        source=query.source,
        resource_type=query.resource_type,
        page=query.page,
        per_page=query.per_page,
    ).as_dict()


@admin_router.get("/sync-runs/{run_id}")
def get_integration_sync_run(
    run_id: int,
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(IntegrationSyncRun, IntegrationSyncCheckpoint, IntegrationConnection)
        .join(
            IntegrationSyncCheckpoint,
            IntegrationSyncCheckpoint.id == IntegrationSyncRun.checkpoint_id,
        )
        .join(
            IntegrationConnection,
            IntegrationConnection.id == IntegrationSyncCheckpoint.connection_id,
        )
        .where(IntegrationSyncRun.id == run_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "sync_run_not_found"})
    return sync_run_view(row[0], row[1], row[2])


def create_integration_export(
    payload: ExportCreateRequest,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("create_export")
    ),
):
    session_digest = integration_actor_digest(claims)
    try:
        export_job = create_export_job(
            db,
            requester_session_digest=session_digest,
            request=payload,
            now=utc_now(),
        )
    except ExportRequestConflict:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="create_export",
            target_id=payload.filters.connection_id or 0,
            reason="connection_not_exportable",
        )
        raise HTTPException(
            status_code=409,
            detail={"code": "connection_not_exportable"},
        ) from None
    except SQLAlchemyError:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="create_export",
            target_id=0,
            reason="persistence_failed",
        )
        raise HTTPException(
            status_code=500,
            detail={"code": "export_persistence_failed"},
        ) from None
    write_security_audit(
        db,
        event_type="integration_export_created",
        outcome="success",
        summary_code="integration_export_created",
        session_digest=session_digest,
        target_type="integration_export",
        target_id=export_job.public_id,
        details={
            "resource_type": payload.resource_type.value,
            "format": payload.format,
        },
    )
    db.commit()
    return export_job_view(export_job, now=utc_now())


def get_integration_export(
    public_id: str,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
):
    try:
        export_job = get_export_job(db, public_id)
    except ValueError:
        export_job = None
    if export_job is None:
        raise HTTPException(status_code=404, detail={"code": "export_not_found"})
    view = export_job_view(export_job, now=utc_now())
    write_security_audit(
        db,
        event_type="integration_export_polled",
        outcome="success",
        summary_code="integration_export_polled",
        session_digest=integration_actor_digest(claims),
        target_type="integration_export",
        target_id=export_job.public_id,
        details={"creator_session_digest": export_job.requester_session_digest},
    )
    db.commit()
    return view


def download_integration_export(
    public_id: str,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
):
    try:
        export_job = get_export_job(db, public_id)
    except ValueError:
        export_job = None
    if export_job is None:
        raise HTTPException(status_code=404, detail={"code": "export_not_found"})
    now = utc_now()
    if export_job.expires_at <= now:
        # Retention owns the file-first transition to EXPIRED. Marking the row
        # here would make cleanup skip the still-present artifact.
        raise HTTPException(status_code=410, detail={"code": "export_expired"})
    if export_job.status is not ExportStatus.READY or not export_job.relative_file_path:
        raise HTTPException(status_code=409, detail={"code": "export_not_ready"})
    settings = _credential_settings_or_503()
    try:
        path = resolve_export_path(
            archive_dir=settings.archive_dir,
            relative_path=export_job.relative_file_path,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "export_file_missing"}) from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "export_file_missing"})
    write_security_audit(
        db,
        event_type="integration_export_downloaded",
        outcome="success",
        summary_code="integration_export_downloaded",
        session_digest=integration_actor_digest(claims),
        target_type="integration_export",
        target_id=export_job.public_id,
        details={"creator_session_digest": export_job.requester_session_digest},
    )
    db.commit()
    media_type = (
        "text/csv; charset=utf-8"
        if export_job.format == "csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"integration-{export_job.public_id}.{export_job.format}",
        headers={"Cache-Control": "no-store"},
    )


def put_integration_product_link(
    commerce_product_id: int,
    payload: ProductLinkUpdate,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("update_product_link", "commerce_product_id")
    ),
):
    if commerce_product_id <= 0:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="update_product_link",
            target_id=commerce_product_id,
            reason="product_not_found",
        )
        raise HTTPException(status_code=404, detail={"code": "product_not_found"})
    commerce_product = db.scalar(
        select(CommerceProduct)
        .where(CommerceProduct.id == commerce_product_id)
        .with_for_update()
    )
    internal_product = db.scalar(select(Product).where(Product.id == payload.product_id))
    if commerce_product is None or internal_product is None:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="update_product_link",
            target_id=commerce_product_id,
            reason="product_not_found",
            provider=(commerce_product.provider if commerce_product is not None else None),
        )
        raise HTTPException(status_code=404, detail={"code": "product_not_found"})
    session_digest = integration_actor_digest(claims)
    now = datetime.now(timezone.utc)
    db.execute(
        postgres_insert(CommerceProductLink)
        .values(
            commerce_product_id=commerce_product.id,
            product_id=internal_product.id,
            linked_by_session_digest=session_digest,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_commerce_product_links_commerce_product",
            set_={
                "product_id": internal_product.id,
                "linked_by_session_digest": session_digest,
                "updated_at": now,
            },
        )
    )
    write_security_audit(
        db,
        event_type="commerce_product_link_updated",
        outcome="success",
        summary_code="commerce_product_link_updated",
        session_digest=session_digest,
        provider=commerce_product.provider,
        target_type="commerce_product",
        target_id=str(commerce_product.id),
        details={"product_id": internal_product.id},
    )
    db.commit()
    return {
        "commerce_product_id": commerce_product.id,
        "product_id": internal_product.id,
        "linked": True,
    }


def delete_integration_product_link(
    commerce_product_id: int,
    db: Session = Depends(get_db),
    claims: IntegrationActor = Depends(current_integration_actor),
    _validation_audit: None = Depends(
        _audit_mutation_validation("delete_product_link", "commerce_product_id")
    ),
):
    commerce_product = db.scalar(
        select(CommerceProduct).where(CommerceProduct.id == commerce_product_id)
    )
    if commerce_product is None:
        _commit_mutation_rejection(
            db,
            claims=claims,
            operation="delete_product_link",
            target_id=commerce_product_id,
            reason="product_not_found",
        )
        raise HTTPException(status_code=404, detail={"code": "product_not_found"})
    db.execute(
        delete(CommerceProductLink).where(
            CommerceProductLink.commerce_product_id == commerce_product_id
        )
    )
    session_digest = integration_actor_digest(claims)
    write_security_audit(
        db,
        event_type="commerce_product_link_deleted",
        outcome="success",
        summary_code="commerce_product_link_deleted",
        session_digest=session_digest,
        provider=commerce_product.provider,
        target_type="commerce_product",
        target_id=str(commerce_product.id),
        details={},
    )
    db.commit()
    return {"commerce_product_id": commerce_product.id, "linked": False}


__all__ = ["admin_router", "operations_router", "public_router"]
