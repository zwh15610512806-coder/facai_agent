"""Transactional authorization and account persistence for connector output."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session

from integration_models import IntegrationAuthorization, IntegrationConnection
from integrations.crypto import CredentialPurpose, encrypt_credential
from integrations.types import (
    AccountIdentity,
    AuthorizationStatus,
    ConnectionStatus,
    ConnectionType,
    Provider,
    ResourceType,
    TokenBundle,
    utc_now,
)


_UTC = timezone.utc
_MAX_CREDENTIAL_CHARS = 16_384
_MAX_SCOPE_COUNT = 128
_MAX_REFRESH_LEASE = timedelta(hours=1)


class _UnspecifiedRefreshGeneration:
    pass


_UNSPECIFIED_REFRESH_GENERATION = _UnspecifiedRefreshGeneration()


class ConnectorOutputInvalid(ValueError):
    """Raised without connector values when normalized output is unsafe."""


class ConnectionOwnershipConflict(ValueError):
    """Raised when an account is already attached to another authorization."""


@dataclass(frozen=True, slots=True)
class OAuthPersistenceResult:
    authorization_id: int
    connection_ids: tuple[int, ...]


def _positive_id(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _lease_owner(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("owner must be a non-empty bounded identifier")
    return value


def _refresh_lease_duration(value: object) -> timedelta:
    if (
        not isinstance(value, timedelta)
        or value <= timedelta(0)
        or value > _MAX_REFRESH_LEASE
    ):
        raise ValueError("lease_duration must be positive and at most one hour")
    return value


def _bounded_text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ConnectorOutputInvalid("Connector output is invalid")
    if value != value.strip() or any(ord(character) < 0x20 for character in value):
        raise ConnectorOutputInvalid("Connector output is invalid")
    return value


def _aware_utc_or_none(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectorOutputInvalid("Connector output is invalid")
    return value.astimezone(_UTC)


def _validated_tokens(tokens: TokenBundle) -> tuple[str, str | None, list[str]]:
    if not isinstance(tokens, TokenBundle):
        raise ConnectorOutputInvalid("Connector output is invalid")
    access_token = _bounded_text(tokens.access_token, maximum=_MAX_CREDENTIAL_CHARS)
    refresh_token = (
        _bounded_text(tokens.refresh_token, maximum=_MAX_CREDENTIAL_CHARS)
        if tokens.refresh_token is not None
        else None
    )
    _bounded_text(tokens.external_subject_id, maximum=255)
    _aware_utc_or_none(tokens.access_expires_at)
    _aware_utc_or_none(tokens.refresh_expires_at)
    if not isinstance(tokens.scopes, tuple) or len(tokens.scopes) > _MAX_SCOPE_COUNT:
        raise ConnectorOutputInvalid("Connector output is invalid")
    scopes = [_bounded_text(scope, maximum=255) for scope in tokens.scopes]
    if len(set(scopes)) != len(scopes):
        raise ConnectorOutputInvalid("Connector output is invalid")
    return access_token, refresh_token, scopes


def acquire_authorization_refresh_lease(
    db: Session,
    *,
    authorization_id: int,
    owner: str,
    now: datetime,
    lease_duration: timedelta,
    expected_last_refreshed_at: (
        datetime | None | _UnspecifiedRefreshGeneration
    ) = _UNSPECIFIED_REFRESH_GENERATION,
) -> bool:
    """Conditionally stage one authorization-wide refresh lease."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    selected_id = _positive_id(
        authorization_id,
        field_name="authorization_id",
    )
    selected_owner = _lease_owner(owner)
    selected_now = _aware_utc_or_none(now)
    assert selected_now is not None
    duration = _refresh_lease_duration(lease_duration)
    generation_condition = None
    if not isinstance(
        expected_last_refreshed_at,
        _UnspecifiedRefreshGeneration,
    ):
        selected_generation = _aware_utc_or_none(expected_last_refreshed_at)
        generation_condition = (
            IntegrationAuthorization.last_refreshed_at.is_(None)
            if selected_generation is None
            else IntegrationAuthorization.last_refreshed_at
            == selected_generation
        )
    conditions = [
        IntegrationAuthorization.id == selected_id,
        IntegrationAuthorization.status == AuthorizationStatus.ACTIVE,
        or_(
            IntegrationAuthorization.refresh_lease_owner.is_(None),
            IntegrationAuthorization.refresh_lease_expires_at.is_(None),
            IntegrationAuthorization.refresh_lease_expires_at <= selected_now,
        ),
    ]
    if generation_condition is not None:
        conditions.append(generation_condition)
    statement = (
        update(IntegrationAuthorization)
        .where(*conditions)
        .values(
            refresh_lease_owner=selected_owner,
            refresh_lease_expires_at=selected_now + duration,
            updated_at=selected_now,
        )
        .returning(IntegrationAuthorization.id)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def release_authorization_refresh_lease(
    db: Session,
    *,
    authorization_id: int,
    owner: str,
    now: datetime,
) -> bool:
    """Release only a refresh lease held by ``owner``."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    selected_id = _positive_id(
        authorization_id,
        field_name="authorization_id",
    )
    selected_owner = _lease_owner(owner)
    selected_now = _aware_utc_or_none(now)
    assert selected_now is not None
    statement = (
        update(IntegrationAuthorization)
        .where(
            IntegrationAuthorization.id == selected_id,
            IntegrationAuthorization.refresh_lease_owner == selected_owner,
        )
        .values(
            refresh_lease_owner=None,
            refresh_lease_expires_at=None,
            updated_at=selected_now,
        )
        .returning(IntegrationAuthorization.id)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def replace_refreshed_authorization_tokens(
    db: Session,
    *,
    authorization_id: int,
    owner: str,
    tokens: TokenBundle,
    master_key: bytes,
    now: datetime,
) -> bool:
    """Atomically rotate all credential fields under a live refresh lease."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    selected_id = _positive_id(
        authorization_id,
        field_name="authorization_id",
    )
    selected_owner = _lease_owner(owner)
    selected_now = _aware_utc_or_none(now)
    assert selected_now is not None
    access_token, refresh_token, scopes = _validated_tokens(tokens)
    external_subject_id = _bounded_text(
        tokens.external_subject_id,
        maximum=255,
    )
    access_ciphertext = encrypt_credential(
        access_token,
        master_key=master_key,
        purpose=CredentialPurpose.ACCESS_TOKEN,
    )
    refresh_ciphertext = (
        encrypt_credential(
            refresh_token,
            master_key=master_key,
            purpose=CredentialPurpose.REFRESH_TOKEN,
        )
        if refresh_token is not None
        else None
    )
    statement = (
        update(IntegrationAuthorization)
        .where(
            IntegrationAuthorization.id == selected_id,
            IntegrationAuthorization.external_subject_id == external_subject_id,
            IntegrationAuthorization.status == AuthorizationStatus.ACTIVE,
            IntegrationAuthorization.refresh_lease_owner == selected_owner,
            IntegrationAuthorization.refresh_lease_expires_at > selected_now,
        )
        .values(
            scopes=scopes,
            access_token_ciphertext=access_ciphertext,
            access_token_tail=access_token[-4:],
            refresh_token_ciphertext=refresh_ciphertext,
            refresh_token_tail=(
                refresh_token[-4:] if refresh_token is not None else None
            ),
            access_expires_at=_aware_utc_or_none(tokens.access_expires_at),
            refresh_expires_at=_aware_utc_or_none(tokens.refresh_expires_at),
            last_refreshed_at=selected_now,
            refresh_lease_owner=None,
            refresh_lease_expires_at=None,
            updated_at=selected_now,
        )
        .returning(IntegrationAuthorization.id)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def mark_authorization_reauthorization_required(
    db: Session,
    *,
    authorization_id: int,
    now: datetime,
) -> int:
    """Clear stored credentials and mark every child connection for OAuth."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    selected_id = _positive_id(
        authorization_id,
        field_name="authorization_id",
    )
    selected_now = _aware_utc_or_none(now)
    assert selected_now is not None
    authorization = db.scalar(
        select(IntegrationAuthorization)
        .where(IntegrationAuthorization.id == selected_id)
        .with_for_update()
    )
    if authorization is None:
        raise ValueError("authorization_id does not reference an authorization")
    if authorization.status in (
        AuthorizationStatus.REVOKED,
        AuthorizationStatus.DISABLED,
    ):
        return 0
    authorization.access_token_ciphertext = ""
    authorization.access_token_tail = ""
    authorization.refresh_token_ciphertext = None
    authorization.refresh_token_tail = None
    authorization.access_expires_at = None
    authorization.refresh_expires_at = None
    authorization.refresh_lease_owner = None
    authorization.refresh_lease_expires_at = None
    authorization.status = AuthorizationStatus.REAUTHORIZATION_REQUIRED
    authorization.updated_at = selected_now
    child_ids = db.scalars(
        select(IntegrationConnection.id).where(
            IntegrationConnection.authorization_id == selected_id
        )
    ).all()
    if child_ids:
        db.execute(
            update(IntegrationConnection)
            .where(IntegrationConnection.id.in_(child_ids))
            .values(
                status=ConnectionStatus.REAUTHORIZATION_REQUIRED,
                updated_at=selected_now,
            )
        )
    db.flush()
    return len(child_ids)


def mark_connection_permission_limited(
    db: Session,
    *,
    connection_id: int,
    resource: ResourceType,
    now: datetime,
) -> bool:
    """Persist one safe resource-level permission reason."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    selected_id = _positive_id(connection_id, field_name="connection_id")
    if not isinstance(resource, ResourceType):
        raise ValueError("resource must be a ResourceType")
    selected_now = _aware_utc_or_none(now)
    assert selected_now is not None
    connection = db.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.id == selected_id)
        .with_for_update()
    )
    if connection is None:
        return False
    existing_report = (
        dict(connection.capability_report)
        if isinstance(connection.capability_report, Mapping)
        else {}
    )
    existing_resources = existing_report.get("resources")
    resources = (
        dict(existing_resources)
        if isinstance(existing_resources, Mapping)
        else {}
    )
    resources[resource.value] = {
        "available": False,
        "reason": "permission_denied",
    }
    existing_report["resources"] = resources
    connection.capability_report = existing_report
    connection.status = ConnectionStatus.PERMISSION_LIMITED
    connection.updated_at = selected_now
    db.flush((connection,))
    return True


def _validated_accounts(
    accounts: list[AccountIdentity],
) -> list[AccountIdentity]:
    if not isinstance(accounts, list) or not accounts:
        raise ConnectorOutputInvalid("Connector output is invalid")
    selected: list[AccountIdentity] = []
    seen: set[tuple[ConnectionType, str]] = set()
    for account in accounts:
        if not isinstance(account, AccountIdentity) or not isinstance(
            account.connection_type, ConnectionType
        ):
            raise ConnectorOutputInvalid("Connector output is invalid")
        external_id = _bounded_text(account.external_account_id, maximum=255)
        _bounded_text(account.display_name, maximum=255)
        identity = (account.connection_type, external_id)
        if identity in seen:
            raise ConnectorOutputInvalid("Connector output is invalid")
        seen.add(identity)
        selected.append(account)
    return selected


def persist_oauth_result(
    db: Session,
    *,
    provider: Provider,
    tokens: TokenBundle,
    accounts: list[AccountIdentity],
    master_key: bytes,
    now: datetime | None = None,
) -> OAuthPersistenceResult:
    """Stage one encrypted authorization and all accounts in one transaction."""

    if not isinstance(provider, Provider):
        raise TypeError("OAuth provider must be a Provider")
    checked_at = utc_now() if now is None else _aware_utc_or_none(now)
    assert checked_at is not None
    access_token, refresh_token, scopes = _validated_tokens(tokens)
    safe_accounts = _validated_accounts(accounts)
    external_subject_id = _bounded_text(tokens.external_subject_id, maximum=255)

    access_ciphertext = encrypt_credential(
        access_token,
        master_key=master_key,
        purpose=CredentialPurpose.ACCESS_TOKEN,
    )
    refresh_ciphertext = (
        encrypt_credential(
            refresh_token,
            master_key=master_key,
            purpose=CredentialPurpose.REFRESH_TOKEN,
        )
        if refresh_token is not None
        else None
    )
    inserted_authorization_id = db.execute(
        postgres_insert(IntegrationAuthorization)
        .values(
            provider=provider,
            external_subject_id=external_subject_id,
            scopes=scopes,
            access_token_ciphertext=access_ciphertext,
            access_token_tail=access_token[-4:],
            refresh_token_ciphertext=refresh_ciphertext,
            refresh_token_tail=(
                refresh_token[-4:] if refresh_token is not None else None
            ),
            access_expires_at=_aware_utc_or_none(tokens.access_expires_at),
            refresh_expires_at=_aware_utc_or_none(tokens.refresh_expires_at),
            status=AuthorizationStatus.ACTIVE,
            last_authorized_at=checked_at,
            created_at=checked_at,
            updated_at=checked_at,
        )
        .on_conflict_do_nothing(
            index_elements=[
                IntegrationAuthorization.provider,
                IntegrationAuthorization.external_subject_id,
            ]
        )
        .returning(IntegrationAuthorization.id)
    ).scalar_one_or_none()
    authorization = db.execute(
        select(IntegrationAuthorization)
        .where(
            (
                IntegrationAuthorization.id == inserted_authorization_id
                if inserted_authorization_id is not None
                else (
                    (IntegrationAuthorization.provider == provider)
                    & (
                        IntegrationAuthorization.external_subject_id
                        == external_subject_id
                    )
                )
            )
        )
        .with_for_update()
    ).scalar_one()
    authorization.scopes = scopes
    authorization.access_token_ciphertext = access_ciphertext
    authorization.access_token_tail = access_token[-4:]
    authorization.refresh_token_ciphertext = refresh_ciphertext
    authorization.refresh_token_tail = (
        refresh_token[-4:] if refresh_token is not None else None
    )
    authorization.access_expires_at = _aware_utc_or_none(tokens.access_expires_at)
    authorization.refresh_expires_at = _aware_utc_or_none(tokens.refresh_expires_at)
    authorization.status = AuthorizationStatus.ACTIVE
    authorization.last_authorized_at = checked_at
    authorization.last_refreshed_at = None
    authorization.refresh_lease_owner = None
    authorization.refresh_lease_expires_at = None
    authorization.updated_at = checked_at
    db.flush()

    connection_ids: list[int] = []
    for account in safe_accounts:
        inserted_connection_id = db.execute(
            postgres_insert(IntegrationConnection)
            .values(
                authorization_id=authorization.id,
                provider=provider,
                connection_type=account.connection_type,
                external_account_id=account.external_account_id,
                display_name=account.display_name,
                status=ConnectionStatus.SETUP_REQUIRED,
                capability_report={},
                created_at=checked_at,
                updated_at=checked_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    IntegrationConnection.provider,
                    IntegrationConnection.connection_type,
                    IntegrationConnection.external_account_id,
                ]
            )
            .returning(IntegrationConnection.id)
        ).scalar_one_or_none()
        connection = db.execute(
            select(IntegrationConnection)
            .where(
                (
                    IntegrationConnection.id == inserted_connection_id
                    if inserted_connection_id is not None
                    else (
                        (IntegrationConnection.provider == provider)
                        & (
                            IntegrationConnection.connection_type
                            == account.connection_type
                        )
                        & (
                            IntegrationConnection.external_account_id
                            == account.external_account_id
                        )
                    )
                )
            )
            .with_for_update()
        ).scalar_one()
        if connection.authorization_id != authorization.id:
            raise ConnectionOwnershipConflict("Connection ownership conflict")
        connection.display_name = account.display_name
        connection.updated_at = checked_at
        connection_ids.append(connection.id)
    return OAuthPersistenceResult(
        authorization_id=authorization.id,
        connection_ids=tuple(connection_ids),
    )


__all__ = [
    "ConnectionOwnershipConflict",
    "ConnectorOutputInvalid",
    "OAuthPersistenceResult",
    "acquire_authorization_refresh_lease",
    "mark_authorization_reauthorization_required",
    "mark_connection_permission_limited",
    "persist_oauth_result",
    "release_authorization_refresh_lease",
    "replace_refreshed_authorization_tokens",
]
