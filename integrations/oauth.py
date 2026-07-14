"""One-time OAuth state creation and atomic consumption."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import update
from sqlalchemy.orm import Session

from integration_models import IntegrationOAuthState
from integrations.types import Provider


_STATE_LIFETIME = timedelta(minutes=10)
_ROOT_RETURN_PATH = "/app/api-connections"
_UTC = timezone.utc


class OAuthStateInvalid(ValueError):
    """Generic state error that never includes raw callback input."""


def _aware_utc(value: datetime | None) -> datetime:
    selected = datetime.now(_UTC) if value is None else value
    if selected.tzinfo is None or selected.utcoffset() is None:
        raise ValueError("OAuth time must be timezone-aware")
    return selected.astimezone(_UTC)


def validate_return_path(return_path: str) -> str:
    if (
        not isinstance(return_path, str)
        or not 1 <= len(return_path) <= 2048
        or "%" in return_path
        or "\\" in return_path
        or "//" in return_path
        or any(
            ord(character) <= 0x20 or ord(character) == 0x7F
            for character in return_path
        )
    ):
        raise ValueError("OAuth return path is invalid")
    try:
        parsed = urlsplit(return_path)
    except ValueError:
        raise ValueError("OAuth return path is invalid") from None
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("OAuth return path is invalid")
    path = parsed.path
    if path == _ROOT_RETURN_PATH:
        return path
    prefix = _ROOT_RETURN_PATH + "/"
    if not path.startswith(prefix) or path == prefix:
        raise ValueError("OAuth return path is invalid")
    segments = path[len(prefix) :].split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError("OAuth return path is invalid")
    return path


def _state_hash(raw_state: str) -> str:
    return hashlib.sha256(raw_state.encode("ascii")).hexdigest()


def create_oauth_state(
    db: Session,
    *,
    provider: Provider,
    session_id: str,
    return_path: str,
    now: datetime | None = None,
) -> str:
    if not isinstance(provider, Provider):
        raise TypeError("OAuth provider must be a Provider")
    if not isinstance(session_id, str) or not session_id or len(session_id) > 512:
        raise ValueError("OAuth initiating session is invalid")
    try:
        encoded_session = session_id.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("OAuth initiating session is invalid") from None
    checked_at = _aware_utc(now)
    safe_return_path = validate_return_path(return_path)
    raw_state = secrets.token_urlsafe(32)
    db.add(
        IntegrationOAuthState(
            state_hash=_state_hash(raw_state),
            provider=provider,
            initiating_session_digest=hashlib.sha256(encoded_session).hexdigest(),
            return_path=safe_return_path,
            created_at=checked_at,
            expires_at=checked_at + _STATE_LIFETIME,
        )
    )
    return raw_state


def consume_oauth_state(
    db: Session,
    *,
    raw_state: str,
    provider: Provider,
    now: datetime | None = None,
) -> IntegrationOAuthState:
    if not isinstance(provider, Provider):
        raise TypeError("OAuth provider must be a Provider")
    if not isinstance(raw_state, str) or not 1 <= len(raw_state) <= 256:
        raise OAuthStateInvalid("OAuth state is invalid")
    try:
        digest = _state_hash(raw_state)
    except (UnicodeEncodeError, ValueError):
        raise OAuthStateInvalid("OAuth state is invalid") from None
    checked_at = _aware_utc(now)
    state = db.execute(
        update(IntegrationOAuthState)
        .where(
            IntegrationOAuthState.state_hash == digest,
            IntegrationOAuthState.provider == provider,
            IntegrationOAuthState.consumed_at.is_(None),
            IntegrationOAuthState.expires_at > checked_at,
        )
        .values(consumed_at=checked_at)
        .returning(IntegrationOAuthState)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if state is None:
        raise OAuthStateInvalid("OAuth state is invalid")
    return state


__all__ = [
    "OAuthStateInvalid",
    "consume_oauth_state",
    "create_oauth_state",
    "validate_return_path",
]
