"""Allowlisted security-audit persistence for integration administration."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Mapping

from sqlalchemy.orm import Session

from integration_models import IntegrationSecurityAudit
from integrations.redaction import assert_payload_safe
from integrations.types import Provider, utc_now


_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TARGET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")


def _bounded_integer(value: object, *, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _one_of(*values: str) -> Callable[[object], bool]:
    allowed = frozenset(values)
    return lambda value: type(value) is str and value in allowed


_EVENT_RULES: dict[str, dict[str, Any]] = {
    "login_succeeded": {
        "outcome": "success",
        "summary_codes": frozenset({"password_verified"}),
        "details": {},
    },
    "login_failed": {
        "outcome": "failure",
        "summary_codes": frozenset({"password_mismatch"}),
        "details": {
            "attempt_count": lambda value: _bounded_integer(
                value, minimum=1, maximum=4
            )
        },
    },
    "login_locked": {
        "outcome": "denied",
        "summary_codes": frozenset({"throttle_locked"}),
        "details": {
            "retry_after_seconds": lambda value: _bounded_integer(
                value, minimum=1, maximum=900
            )
        },
    },
    "login_rejected": {
        "outcome": "denied",
        "summary_codes": frozenset(
            {
                "https_required",
                "login_not_configured",
                "transport_configuration_invalid",
            }
        ),
        "details": {
            "reason": _one_of(
                "https_required",
                "login_not_configured",
                "transport_configuration_invalid",
            )
        },
    },
    "session_deleted": {
        "outcome": "success",
        "summary_codes": frozenset({"session_deleted"}),
        "details": {},
    },
    "app_config_changed": {
        "outcome": "success",
        "summary_codes": frozenset(
            {
                "app_config_created",
                "app_config_updated",
                "app_secret_cleared",
            }
        ),
        "details": {},
    },
    "oauth_callback_succeeded": {
        "outcome": "success",
        "summary_codes": frozenset({"oauth_completed"}),
        "details": {},
    },
    "oauth_callback_failed": {
        "outcome": "failure",
        "summary_codes": frozenset({"oauth_completion_failed"}),
        "details": {
            "stage": _one_of(
                "callback_input",
                "connector_lookup",
                "exchange",
                "discovery",
                "persistence",
            )
        },
    },
    "manual_sync_enqueued": {
        "outcome": "success",
        "summary_codes": frozenset({"manual_sync_enqueued"}),
        "details": {
            "resource_count": lambda value: _bounded_integer(
                value, minimum=1, maximum=15
            ),
            "unit_count": lambda value: _bounded_integer(
                value, minimum=1, maximum=10_000
            ),
        },
        "target_type": "connection",
        "provider": "required",
        "session_required": True,
    },
    "connection_disabled": {
        "outcome": "success",
        "summary_codes": frozenset({"connection_disabled"}),
        "details": {},
        "target_type": "connection",
        "provider": "required",
        "session_required": True,
    },
    "authorization_disabled": {
        "outcome": "success",
        "summary_codes": frozenset({"authorization_disabled_locally"}),
        "details": {
            "child_connection_count": lambda value: _bounded_integer(
                value, minimum=0, maximum=1_000_000
            ),
            "platform_revoke": _one_of("succeeded", "failed", "unavailable"),
        },
        "target_type": "authorization",
        "provider": "required",
        "session_required": True,
    },
    "connection_purge_enqueued": {
        "outcome": "success",
        "summary_codes": frozenset({"connection_purge_enqueued"}),
        "details": {
            "job_id": lambda value: _bounded_integer(
                value, minimum=1, maximum=9_223_372_036_854_775_807
            )
        },
        "target_type": "connection",
        "provider": "required",
        "session_required": True,
    },
    "sync_run_retry_enqueued": {
        "outcome": "success",
        "summary_codes": frozenset({"sync_run_retry_enqueued"}),
        "details": {
            "child_run_id": lambda value: _bounded_integer(
                value, minimum=1, maximum=9_223_372_036_854_775_807
            ),
            "job_id": lambda value: _bounded_integer(
                value, minimum=1, maximum=9_223_372_036_854_775_807
            ),
        },
        "target_type": "sync_run",
        "provider": "required",
        "session_required": True,
    },
    "integration_export_created": {
        "outcome": "success",
        "summary_codes": frozenset({"integration_export_created"}),
        "details": {
            "resource_type": _one_of(
                "orders",
                "products",
                "refunds",
                "ad_entities",
                "ad_daily_metrics",
            ),
            "format": _one_of("csv", "xlsx"),
        },
        "target_type": "integration_export",
        "provider": "forbidden",
        "session_required": True,
    },
    "integration_export_polled": {
        "outcome": "success",
        "summary_codes": frozenset({"integration_export_polled"}),
        "details": {"creator_session_digest": lambda value: bool(_HEX_DIGEST.fullmatch(value)) if isinstance(value, str) else False},
        "target_type": "integration_export",
        "provider": "forbidden",
        "session_required": True,
    },
    "integration_export_downloaded": {
        "outcome": "success",
        "summary_codes": frozenset({"integration_export_downloaded"}),
        "details": {"creator_session_digest": lambda value: bool(_HEX_DIGEST.fullmatch(value)) if isinstance(value, str) else False},
        "target_type": "integration_export",
        "provider": "forbidden",
        "session_required": True,
    },
    "commerce_product_link_updated": {
        "outcome": "success",
        "summary_codes": frozenset({"commerce_product_link_updated"}),
        "details": {
            "product_id": lambda value: _bounded_integer(
                value, minimum=1, maximum=9_223_372_036_854_775_807
            )
        },
        "target_type": "commerce_product",
        "provider": "required",
        "session_required": True,
    },
    "commerce_product_link_deleted": {
        "outcome": "success",
        "summary_codes": frozenset({"commerce_product_link_deleted"}),
        "details": {},
        "target_type": "commerce_product",
        "provider": "required",
        "session_required": True,
    },
    "integration_mutation_rejected": {
        "outcome": "failure",
        "summary_codes": frozenset({"integration_mutation_rejected"}),
        "details": {
            "operation": _one_of(
                "manual_sync",
                "update_app_config",
                "start_authorization",
                "reauthorize",
                "disable_connection",
                "disable_authorization",
                "purge_connection",
                "retry_sync_run",
                "create_export",
                "update_product_link",
                "delete_product_link",
            ),
            "reason": _one_of(
                "connection_not_found",
                "authorization_not_found",
                "sync_not_available",
                "connector_unavailable",
                "provider_app_not_configured",
                "invalid_return_path",
                "confirmation_mismatch",
                "sync_run_not_found",
                "sync_run_not_retryable",
                "product_not_found",
                "persistence_failed",
                "validation_rejected",
                "connection_not_exportable",
            ),
        },
        "target_type": "integration_command",
        "provider": "optional",
        "session_required": True,
    },
    "authorization_start_succeeded": {
        "outcome": "success",
        "summary_codes": frozenset({"authorization_start_succeeded"}),
        "details": {},
        "target_type": "authorization_start",
        "provider": "required",
        "session_required": True,
    },
    "authorization_start_rejected": {
        "outcome": "failure",
        "summary_codes": frozenset({"authorization_start_rejected"}),
        "details": {
            "reason": _one_of(
                "security_configuration_incomplete",
                "invalid_return_path",
                "provider_app_not_configured",
                "connector_unavailable",
                "connector_authorization_unavailable",
            )
        },
        "target_type": "authorization_start",
        "provider": "required",
        "session_required": True,
    },
}


def _validate_digest(value: str | None, *, field_name: str) -> None:
    if value is not None and (
        not isinstance(value, str) or _HEX_DIGEST.fullmatch(value) is None
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _validated_details(
    *,
    event_type: str,
    outcome: str,
    summary_code: str,
    details: Mapping[str, Any] | None,
) -> dict[str, Any]:
    rule = _EVENT_RULES.get(event_type)
    if rule is None:
        raise ValueError("Security audit event type is not allowlisted")
    if outcome != rule["outcome"]:
        raise ValueError("Security audit outcome is not allowlisted for this event")
    if summary_code not in rule["summary_codes"]:
        raise ValueError("Security audit summary is not allowlisted for this event")
    selected = dict(details or {})
    validators: dict[str, Callable[[object], bool]] = rule["details"]
    if set(selected) != set(validators):
        raise ValueError("Security audit details do not match the event allowlist")
    assert_payload_safe(selected)
    if any(not validators[key](selected[key]) for key in validators):
        raise ValueError("Security audit detail value is invalid")
    return selected


def write_security_audit(
    db: Session,
    *,
    event_type: str,
    outcome: str,
    summary_code: str,
    source_digest: str | None = None,
    session_digest: str | None = None,
    provider: Provider | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
) -> IntegrationSecurityAudit:
    """Stage a sanitized, event-specific security audit row in ``db``."""

    _validate_digest(source_digest, field_name="source_digest")
    _validate_digest(session_digest, field_name="session_digest")
    safe_details = _validated_details(
        event_type=event_type,
        outcome=outcome,
        summary_code=summary_code,
        details=details,
    )
    rule = _EVENT_RULES[event_type]
    if event_type == "app_config_changed":
        if (
            session_digest is None
            or not isinstance(provider, Provider)
            or target_type != "app_config"
            or target_id != provider.value
        ):
            raise ValueError(
                "App-config audits require the allowlisted provider target"
            )
    elif event_type in {"oauth_callback_succeeded", "oauth_callback_failed"}:
        if (
            session_digest is None
            or not isinstance(provider, Provider)
            or target_type != "oauth"
            or target_id != provider.value
        ):
            raise ValueError("OAuth audits require the allowlisted provider target")
    elif "target_type" in rule:
        provider_policy = rule["provider"]
        if (
            (rule["session_required"] and session_digest is None)
            or target_type != rule["target_type"]
            or not isinstance(target_id, str)
            or _SAFE_TARGET_ID.fullmatch(target_id) is None
            or (provider_policy == "required" and not isinstance(provider, Provider))
            or (provider_policy == "forbidden" and provider is not None)
            or (
                provider_policy == "optional"
                and provider is not None
                and not isinstance(provider, Provider)
            )
        ):
            raise ValueError("Administration audits require an allowlisted target")
    elif target_type is not None or target_id is not None or provider is not None:
        raise ValueError("Login security audits cannot include a provider or target")
    audit = IntegrationSecurityAudit(
        event_type=event_type,
        outcome=outcome,
        source_digest=source_digest,
        session_digest=session_digest,
        provider=provider,
        target_type=target_type,
        target_id=target_id,
        summary_code=summary_code,
        details=safe_details,
        created_at=created_at or utc_now(),
    )
    db.add(audit)
    return audit


__all__ = ["write_security_audit"]
