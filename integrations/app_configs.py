"""Encrypted provider app configuration without credential read exposure."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update as sql_update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session

from integration_models import IntegrationAppConfig
from integrations.audit import write_security_audit
from integrations.crypto import CredentialPurpose, encrypt_credential
from integrations.schemas import (
    AppConfigUpdate,
    AppConfigView,
    ProviderIntegrationView,
    ProviderListResponse,
)
from integrations.types import Provider, utc_now


_CONFIGURED = "configured"
_SETUP_REQUIRED = "setup_required"
_NOT_CONFIGURED = "not_configured"
_LIVE_STATUS_PENDING = "pending"


def _secret_mask(secret_tail: str | None) -> str | None:
    if secret_tail is None:
        return None
    return f"****{secret_tail}"


def _safe_view(
    *,
    provider: Provider,
    app_id: str | None,
    secret_tail: str | None,
    status: str,
    updated_at: datetime | None,
) -> AppConfigView:
    return AppConfigView(
        provider=provider,
        app_id=app_id,
        secret_configured=secret_tail is not None,
        secret_mask=_secret_mask(secret_tail),
        status=status,
        updated_at=updated_at,
    )


def list_provider_app_configs(db: Session) -> ProviderListResponse:
    """List every documented provider using selected non-secret columns only."""

    rows = db.execute(
        select(
            IntegrationAppConfig.provider,
            IntegrationAppConfig.app_id,
            IntegrationAppConfig.app_secret_tail,
            IntegrationAppConfig.status,
            IntegrationAppConfig.updated_at,
        )
    ).all()
    configured_by_provider: dict[Provider, AppConfigView] = {}
    for row in rows:
        provider = (
            row.provider
            if isinstance(row.provider, Provider)
            else Provider(row.provider)
        )
        configured_by_provider[provider] = _safe_view(
            provider=provider,
            app_id=row.app_id,
            secret_tail=row.app_secret_tail,
            status=row.status,
            updated_at=row.updated_at,
        )

    providers: list[ProviderIntegrationView] = []
    for provider in Provider:
        app_config = configured_by_provider.get(provider)
        if app_config is None:
            app_config = _safe_view(
                provider=provider,
                app_id=None,
                secret_tail=None,
                status=_NOT_CONFIGURED,
                updated_at=None,
            )
        providers.append(
            ProviderIntegrationView(
                provider=provider,
                documented=True,
                configured=(
                    app_config.status == _CONFIGURED
                    and app_config.secret_configured
                ),
                live_verified=False,
                live_status=_LIVE_STATUS_PENDING,
                app_config=app_config,
            )
        )
    return ProviderListResponse(providers=providers)


def upsert_provider_app_config(
    db: Session,
    *,
    provider: Provider,
    update: AppConfigUpdate,
    master_key: bytes,
    session_digest: str,
) -> AppConfigView:
    """Stage one encrypted app-config mutation and its audit in one transaction."""

    insert_time = utc_now()
    inserted_id = db.execute(
        postgres_insert(IntegrationAppConfig)
        .values(
            provider=provider,
            app_id=update.app_id,
            app_secret_ciphertext=None,
            app_secret_tail=None,
            status=_SETUP_REQUIRED,
            created_at=insert_time,
            updated_at=insert_time,
        )
        .on_conflict_do_nothing(index_elements=[IntegrationAppConfig.provider])
        .returning(IntegrationAppConfig.id)
    ).scalar_one_or_none()
    created = inserted_id is not None

    current = db.execute(
        select(
            IntegrationAppConfig.id,
            IntegrationAppConfig.app_secret_ciphertext,
            IntegrationAppConfig.app_secret_tail,
        )
        .where(IntegrationAppConfig.provider == provider)
        .with_for_update()
    ).one()
    now = utc_now()
    had_secret = current.app_secret_ciphertext is not None

    secret_value = (
        update.app_secret.get_secret_value()
        if update.app_secret is not None
        else None
    )
    if secret_value is not None:
        next_ciphertext = encrypt_credential(
            secret_value,
            master_key=master_key,
            purpose=CredentialPurpose.APP_SECRET,
        )
        next_tail = secret_value[-4:]
    elif update.clear_secret:
        next_ciphertext = None
        next_tail = None
    else:
        next_ciphertext = current.app_secret_ciphertext
        next_tail = current.app_secret_tail
    next_status = (
        _CONFIGURED
        if next_ciphertext is not None and next_tail is not None
        else _SETUP_REQUIRED
    )

    db.execute(
        sql_update(IntegrationAppConfig)
        .where(IntegrationAppConfig.id == current.id)
        .values(
            app_id=update.app_id,
            app_secret_ciphertext=next_ciphertext,
            app_secret_tail=next_tail,
            status=next_status,
            updated_at=now,
        )
    )
    if created:
        summary_code = "app_config_created"
    elif update.clear_secret and had_secret:
        summary_code = "app_secret_cleared"
    else:
        summary_code = "app_config_updated"
    write_security_audit(
        db,
        event_type="app_config_changed",
        outcome="success",
        summary_code=summary_code,
        session_digest=session_digest,
        provider=provider,
        target_type="app_config",
        target_id=provider.value,
        details={},
        created_at=now,
    )
    return _safe_view(
        provider=provider,
        app_id=update.app_id,
        secret_tail=next_tail,
        status=next_status,
        updated_at=now,
    )


__all__ = ["list_provider_app_configs", "upsert_provider_app_config"]
