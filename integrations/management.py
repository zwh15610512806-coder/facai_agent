"""Safe administration views and provider-neutral integration commands."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from integration_models import IntegrationAuthorization, IntegrationConnection
from integrations.schemas import ManualSyncRequest
from integrations.sync.scheduler import ScheduledUnit, enqueue_scheduled_units
from integrations.types import (
    AuthorizationStatus,
    ConnectionStatus,
    ConnectionType,
    Provider,
    JobType,
    ResourceType,
    TimeWindow,
)


UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")
_SNAPSHOT_RESOURCES = frozenset(
    {
        ResourceType.SHOPS,
        ResourceType.PRODUCTS,
        ResourceType.SKUS,
        ResourceType.INVENTORY,
        ResourceType.AD_ACCOUNTS,
        ResourceType.AD_ENTITIES,
        ResourceType.AD_BALANCE_SNAPSHOTS,
    }
)


class ManagementConflict(ValueError):
    """Closed command rejection without provider or credential details."""


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("management timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _enum_value(value: object, enum_type: type) -> str:
    if not isinstance(value, enum_type):
        raise TypeError("management enum value is invalid")
    return value.value


def _credential_mask(ciphertext: object, tail: object) -> str | None:
    if not isinstance(ciphertext, str) or not ciphertext:
        return None
    if (
        not isinstance(tail, str)
        or len(tail) != 4
        or any(ord(character) < 32 or ord(character) == 127 for character in tail)
    ):
        return None
    return f"••••{tail}"


def _capability_resources(value: object) -> tuple[list[str], list[dict[str, str]]]:
    if not isinstance(value, dict):
        return [], []
    raw_resources = value.get("verified_resources")
    verified: set[str] = set()
    if isinstance(raw_resources, list):
        for item in raw_resources:
            try:
                resource = ResourceType(item)
            except (TypeError, ValueError):
                continue
            verified.add(resource.value)
    limited: list[dict[str, str]] = []
    resource_states = value.get("resources")
    if isinstance(resource_states, dict):
        for raw_resource, raw_state in resource_states.items():
            try:
                resource = ResourceType(raw_resource)
            except (TypeError, ValueError):
                continue
            if not isinstance(raw_state, dict):
                continue
            if raw_state.get("available") is True:
                verified.add(resource.value)
            elif raw_state.get("available") is False:
                verified.discard(resource.value)
                reason = raw_state.get("reason")
                limited.append(
                    {
                        "resource": resource.value,
                        "reason": (
                            reason
                            if isinstance(reason, str)
                            and reason in {"permission_denied", "not_supported"}
                            else "unavailable"
                        ),
                    }
                )
    return sorted(verified), sorted(limited, key=lambda item: item["resource"])


def _capability_summary(value: object) -> dict[str, object]:
    verified, limited = _capability_resources(value)
    return {
        "verified_resources": verified,
        "limited_resources": limited,
        "status": (
            "permission_limited"
            if limited
            else "verified" if verified else "unverified"
        ),
    }


def authorization_view(authorization: object) -> dict[str, object]:
    """Serialize the credential metadata allowlist without any ciphertext."""

    scopes = getattr(authorization, "scopes", [])
    safe_scopes = (
        sorted(scope for scope in scopes if isinstance(scope, str))
        if isinstance(scopes, list)
        else []
    )
    return {
        "id": int(getattr(authorization, "id")),
        "provider": _enum_value(getattr(authorization, "provider"), Provider),
        "status": _enum_value(
            getattr(authorization, "status"),
            AuthorizationStatus,
        ),
        "scopes": safe_scopes,
        "access_token_mask": _credential_mask(
            getattr(authorization, "access_token_ciphertext", None),
            getattr(authorization, "access_token_tail", None),
        ),
        "refresh_token_mask": _credential_mask(
            getattr(authorization, "refresh_token_ciphertext", None),
            getattr(authorization, "refresh_token_tail", None),
        ),
        "access_expires_at": _utc_iso(
            getattr(authorization, "access_expires_at", None)
        ),
        "refresh_expires_at": _utc_iso(
            getattr(authorization, "refresh_expires_at", None)
        ),
        "last_authorized_at": _utc_iso(
            getattr(authorization, "last_authorized_at", None)
        ),
        "last_refreshed_at": _utc_iso(
            getattr(authorization, "last_refreshed_at", None)
        ),
    }


def connection_view(connection: object, authorization: object) -> dict[str, object]:
    return {
        "id": int(getattr(connection, "id")),
        "authorization_id": int(getattr(connection, "authorization_id")),
        "provider": _enum_value(getattr(connection, "provider"), Provider),
        "connection_type": _enum_value(
            getattr(connection, "connection_type"),
            ConnectionType,
        ),
        "external_account_id": str(getattr(connection, "external_account_id")),
        "display_name": str(getattr(connection, "display_name")),
        "status": _enum_value(getattr(connection, "status"), ConnectionStatus),
        "capabilities": _capability_summary(
            getattr(connection, "capability_report", None)
        ),
        "earliest_available_date": (
            getattr(connection, "earliest_available_date").isoformat()
            if getattr(connection, "earliest_available_date", None) is not None
            else None
        ),
        "last_successful_sync_at": _utc_iso(
            getattr(connection, "last_successful_sync_at", None)
        ),
        "disabled_at": _utc_iso(getattr(connection, "disabled_at", None)),
        "authorization": authorization_view(authorization),
    }


def list_connection_views(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(IntegrationConnection, IntegrationAuthorization)
        .join(
            IntegrationAuthorization,
            IntegrationAuthorization.id == IntegrationConnection.authorization_id,
        )
        .order_by(
            IntegrationConnection.provider,
            IntegrationConnection.display_name,
            IntegrationConnection.id,
        )
    ).all()
    return [connection_view(connection, authorization) for connection, authorization in rows]


def get_connection_view(db: Session, connection_id: int) -> dict[str, object] | None:
    if type(connection_id) is not int or connection_id <= 0:
        return None
    row = db.execute(
        select(IntegrationConnection, IntegrationAuthorization)
        .join(
            IntegrationAuthorization,
            IntegrationAuthorization.id == IntegrationConnection.authorization_id,
        )
        .where(IntegrationConnection.id == connection_id)
    ).one_or_none()
    if row is None:
        return None
    return connection_view(row[0], row[1])


def get_authorization_view(
    db: Session,
    authorization_id: int,
) -> dict[str, object] | None:
    if type(authorization_id) is not int or authorization_id <= 0:
        return None
    authorization = db.scalar(
        select(IntegrationAuthorization).where(
            IntegrationAuthorization.id == authorization_id
        )
    )
    return authorization_view(authorization) if authorization is not None else None


def enqueue_manual_sync(
    db: Session,
    *,
    connection_id: int,
    request: ManualSyncRequest,
    now: datetime,
):
    if not isinstance(request, ManualSyncRequest):
        raise TypeError("request must be a ManualSyncRequest")
    selected_now = datetime.fromisoformat(_utc_iso(now).replace("Z", "+00:00"))
    connection = db.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.id == connection_id)
        .with_for_update()
    )
    if connection is None:
        raise LookupError("connection not found")
    if connection.status not in {
        ConnectionStatus.ACTIVE,
        ConnectionStatus.PERMISSION_LIMITED,
    }:
        raise ManagementConflict("connection is not enabled for synchronization")
    report = connection.capability_report if isinstance(connection.capability_report, dict) else {}
    verified_values, _limited = _capability_resources(report)
    verified = {ResourceType(value) for value in verified_values}
    if any(resource not in verified for resource in request.resources):
        raise ManagementConflict("requested resource is not verified")

    units: list[ScheduledUnit] = []
    for resource in request.resources:
        if resource in _SNAPSHOT_RESOURCES:
            slot = selected_now.replace(minute=0, second=0, microsecond=0)
            units.append(
                ScheduledUnit(
                    job_type=JobType.SYNC_RESOURCE,
                    authorization_id=connection.authorization_id,
                    connection_id=connection.id,
                    resource_type=resource,
                    window_start=slot,
                    window_end=slot + timedelta(hours=1),
                    api_window=None,
                    captured_at=slot,
                    schedule_slot=selected_now,
                )
            )
            continue
        current_date = request.date_from
        while current_date <= request.date_to:
            start = datetime.combine(current_date, time.min, tzinfo=SHANGHAI).astimezone(UTC)
            end = datetime.combine(
                current_date + timedelta(days=1),
                time.min,
                tzinfo=SHANGHAI,
            ).astimezone(UTC)
            units.append(
                ScheduledUnit(
                    job_type=JobType.SYNC_RESOURCE,
                    authorization_id=connection.authorization_id,
                    connection_id=connection.id,
                    resource_type=resource,
                    window_start=start,
                    window_end=end,
                    api_window=TimeWindow(start, end),
                    schedule_slot=selected_now,
                )
            )
            current_date += timedelta(days=1)
    result = enqueue_scheduled_units(
        db,
        units,
        manual_request_id=str(request.request_id),
    )
    return result, tuple(units), connection


__all__ = [
    "authorization_view",
    "connection_view",
    "get_authorization_view",
    "get_connection_view",
    "enqueue_manual_sync",
    "list_connection_views",
    "ManagementConflict",
]
