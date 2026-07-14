"""Encrypted, atomic archives for sanitized connector page payloads."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from integration_models import IntegrationArchiveManifest
from integrations.crypto import derive_archive_page_key
from integrations.redaction import (
    PayloadSafetyError,
    assert_payload_safe,
    normalize_payload_key,
)
from integrations.types import NormalizedRecord, Provider, ResourceType


ARCHIVE_ENVELOPE_PREFIX = b"FACAIAR\x01"
_ARCHIVE_NONCE_BYTES = 12
_ARCHIVE_TAG_BYTES = 16
_ARCHIVE_SUFFIX = ".jsonl.gz.aes"
_ORPHAN_MINIMUM_AGE = timedelta(hours=1)
_ARCHIVE_RETENTION = timedelta(days=90)
_SECRET_VALUE = re.compile(
    r"(?ix)"
    r"(?:"
    r"access[\s_-]*token|refresh[\s_-]*token|app[\s_-]*secret|"
    r"client[\s_-]*secret|authorization[\s_-]*code|"
    r"(?:x[\s_-]*)?api[\s_-]*key|proxy[\s_-]*authorization|"
    r"authorization|set[\s_-]*cookie|cookie|token|secret"
    r")"
    r"\s*[\"']?\s*[:=]"
    r"|\bbearer(?:\s|[\"'])+"
)
_EMAIL_VALUE = re.compile(
    r"(?i)(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}(?![\w.-])"
)
_MAINLAND_PHONE_VALUE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_PRC_ID_VALUE = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")


class ArchiveDecryptionError(ValueError):
    """Raised without envelope, path, or payload details."""


class ArchiveWriteError(OSError):
    """A stable write failure that never includes raw OS error details."""


class ArchiveAuditCode(str, Enum):
    """Closed audit events emitted by retention maintenance."""

    FILE_MISSING = "archive_file_missing"


class ArchiveCleanupErrorCode(str, Enum):
    """Closed retry reasons emitted by archive maintenance."""

    INVALID_PATH = "invalid_archive_path"
    DELETE_IO_FAILED = "archive_delete_io_failed"


@dataclass(frozen=True, slots=True)
class ArchiveArtifact:
    relative_path: str
    sha256: str
    record_count: int


@dataclass(frozen=True, slots=True)
class OrphanScanResult:
    deleted_paths: tuple[str, ...]
    failure_codes: tuple[ArchiveCleanupErrorCode, ...]


@dataclass(frozen=True, slots=True)
class ArchiveCleanupResult:
    deleted_count: int
    missing_count: int
    retry_count: int


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    offset = value.utcoffset()
    if offset is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _positive_integer(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _page_number(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 999_999:
        raise ValueError("page_number must be an integer from 0 through 999999")
    return value


def _archive_root(archive_dir: os.PathLike[str] | str, *, create: bool) -> Path:
    try:
        root = Path(os.fspath(archive_dir)).resolve(strict=False)
    except (TypeError, ValueError, OSError) as exc:
        if isinstance(exc, (TypeError, ValueError)):
            raise TypeError("archive_dir must be a filesystem path") from None
        raise ArchiveWriteError("Unable to write archive page") from None
    if create:
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise ArchiveWriteError("Unable to write archive page") from None
    return root


def _relative_parts(relative_path: object) -> tuple[str, ...]:
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or relative_path != relative_path.strip()
        or len(relative_path) > 2048
        or "\\" in relative_path
        or "\x00" in relative_path
        or ":" in relative_path
    ):
        raise ValueError("Archive relative path is invalid")
    path = PurePosixPath(relative_path)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or not relative_path.endswith(_ARCHIVE_SUFFIX)
        or path.as_posix() != relative_path
    ):
        raise ValueError("Archive relative path is invalid")
    return path.parts


def _contained_path(root: Path, relative_path: str) -> Path:
    parts = _relative_parts(relative_path)
    candidate = root.joinpath(*parts).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise ValueError("Archive relative path escapes archive_dir")
    return candidate


def _canonical_relative_path(
    *,
    provider: Provider,
    connection_id: int,
    resource: ResourceType,
    run_id: int,
    page_number: int,
    created_at: datetime,
) -> str:
    if not isinstance(provider, Provider):
        raise TypeError("provider must be a Provider")
    if not isinstance(resource, ResourceType):
        raise TypeError("resource must be a ResourceType")
    selected_connection_id = _positive_integer(
        connection_id,
        field_name="connection_id",
    )
    selected_run_id = _positive_integer(run_id, field_name="run_id")
    selected_page = _page_number(page_number)
    selected_created_at = _aware_utc(created_at, field_name="created_at")
    return (
        f"{provider.value}/{selected_connection_id}/{resource.value}/"
        f"{selected_created_at:%Y/%m}/{selected_run_id}-{selected_page:06d}"
        f"{_ARCHIVE_SUFFIX}"
    )


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        selected = _aware_utc(value, field_name="archive payload datetime")
        return selected.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError("Archive payload contains an unsupported value")


def _is_identifier_field(key: object | None) -> bool:
    if not isinstance(key, str):
        return False
    normalized = normalize_payload_key(key)
    return normalized.endswith(("id", "ids"))


def _assert_archive_values_safe(
    value: object,
    *,
    parent_key: object | None = None,
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _assert_archive_values_safe(child, parent_key=key)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _assert_archive_values_safe(child, parent_key=parent_key)
        return
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        return
    text = str(value)
    has_secret_or_email = any(
        pattern.search(text) is not None
        for pattern in (_SECRET_VALUE, _EMAIL_VALUE)
    )
    has_unscoped_personal_number = not _is_identifier_field(parent_key) and any(
        pattern.search(text) is not None
        for pattern in (_MAINLAND_PHONE_VALUE, _PRC_ID_VALUE)
    )
    if has_secret_or_email or has_unscoped_personal_number:
        raise PayloadSafetyError("Archive payload contains a sensitive value")


def _canonical_jsonl(
    records: Iterable[NormalizedRecord],
    *,
    resource: ResourceType,
) -> tuple[bytes, int]:
    if isinstance(records, (str, bytes, bytearray)):
        raise TypeError("records must contain NormalizedRecord values")
    selected_records = tuple(records)
    lines: list[bytes] = []
    for record in selected_records:
        if not isinstance(record, NormalizedRecord):
            raise TypeError("records must contain NormalizedRecord values")
        if record.resource is not resource:
            raise ValueError("record resource must match archive resource")
        payload = record.source_payload_for_serialization()
        assert_payload_safe(payload)
        _assert_archive_values_safe(payload)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=_json_default,
        ).encode("utf-8")
        lines.append(encoded + b"\n")
    return b"".join(lines), len(selected_records)


def archive_expires_at(created_at: datetime) -> datetime:
    """Return the fixed 90-day expiry for an archive created at ``created_at``."""

    return _aware_utc(created_at, field_name="created_at") + _ARCHIVE_RETENTION


def create_archive_page(
    *,
    archive_dir: os.PathLike[str] | str,
    master_key: bytes,
    provider: Provider,
    connection_id: int,
    resource: ResourceType,
    run_id: int,
    page_number: int,
    created_at: datetime,
    records: Iterable[NormalizedRecord],
) -> ArchiveArtifact:
    """Serialize, encrypt, and atomically publish one sanitized page archive."""

    relative_path = _canonical_relative_path(
        provider=provider,
        connection_id=connection_id,
        resource=resource,
        run_id=run_id,
        page_number=page_number,
        created_at=created_at,
    )
    jsonl, record_count = _canonical_jsonl(records, resource=resource)
    compressed = gzip.compress(jsonl, compresslevel=9, mtime=0)
    key = derive_archive_page_key(master_key)
    nonce = os.urandom(_ARCHIVE_NONCE_BYTES)
    aad = relative_path.encode("utf-8")
    encrypted = ARCHIVE_ENVELOPE_PREFIX + nonce + AESGCM(key).encrypt(
        nonce,
        compressed,
        aad,
    )

    root = _archive_root(archive_dir, create=True)
    final_path = _contained_path(root, relative_path)
    try:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path = _contained_path(root, relative_path)
        file_descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{final_path.name}.",
            suffix=".tmp",
            dir=final_path.parent,
        )
    except OSError:
        raise ArchiveWriteError("Unable to write archive page") from None

    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, final_path)
    except OSError:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ArchiveWriteError("Unable to write archive page") from None

    return ArchiveArtifact(
        relative_path=relative_path,
        sha256=hashlib.sha256(encrypted).hexdigest(),
        record_count=record_count,
    )


def decrypt_archive_bytes(
    envelope: bytes,
    *,
    master_key: bytes,
    relative_path: str,
) -> bytes:
    """Authenticate and decompress one archive without exposing failure details."""

    try:
        if not isinstance(envelope, bytes):
            raise ValueError
        _relative_parts(relative_path)
        minimum_length = (
            len(ARCHIVE_ENVELOPE_PREFIX)
            + _ARCHIVE_NONCE_BYTES
            + _ARCHIVE_TAG_BYTES
        )
        if len(envelope) < minimum_length or not envelope.startswith(
            ARCHIVE_ENVELOPE_PREFIX
        ):
            raise ValueError
        offset = len(ARCHIVE_ENVELOPE_PREFIX)
        nonce = envelope[offset : offset + _ARCHIVE_NONCE_BYTES]
        ciphertext_and_tag = envelope[offset + _ARCHIVE_NONCE_BYTES :]
        compressed = AESGCM(derive_archive_page_key(master_key)).decrypt(
            nonce,
            ciphertext_and_tag,
            relative_path.encode("utf-8"),
        )
        return gzip.decompress(compressed)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise ArchiveDecryptionError("Unable to decrypt archive page") from None


class ArchivePage:
    """Keep an archive only after the surrounding DB transaction is retained."""

    def __init__(
        self,
        *,
        archive_dir: os.PathLike[str] | str,
        master_key: bytes,
        provider: Provider,
        connection_id: int,
        resource: ResourceType,
        run_id: int,
        page_number: int,
        created_at: datetime,
        records: Iterable[NormalizedRecord],
    ) -> None:
        self._create_options = {
            "archive_dir": archive_dir,
            "master_key": master_key,
            "provider": provider,
            "connection_id": connection_id,
            "resource": resource,
            "run_id": run_id,
            "page_number": page_number,
            "created_at": created_at,
            "records": records,
        }
        self._artifact: ArchiveArtifact | None = None
        self._root: Path | None = None
        self._active = False
        self._entered = False
        self._retained = False

    @property
    def artifact(self) -> ArchiveArtifact:
        if self._artifact is None:
            raise RuntimeError("ArchivePage has not created an artifact")
        return self._artifact

    @property
    def relative_path(self) -> str:
        return self.artifact.relative_path

    @property
    def sha256(self) -> str:
        return self.artifact.sha256

    @property
    def record_count(self) -> int:
        return self.artifact.record_count

    def __enter__(self) -> ArchivePage:
        if self._entered:
            raise RuntimeError("ArchivePage cannot be entered more than once")
        self._entered = True
        self._artifact = create_archive_page(**self._create_options)
        self._root = _archive_root(self._create_options["archive_dir"], create=False)
        self._active = True
        return self

    def retain(self) -> None:
        """Mark the file durable after the caller's DB transaction commits."""

        if not self._active:
            raise RuntimeError("ArchivePage is not active")
        self._retained = True

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            if not self._retained:
                final_path = _contained_path(self._root, self.relative_path)
                try:
                    final_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    if exc_type is None:
                        raise ArchiveWriteError(
                            "Unable to remove uncommitted archive page"
                        ) from None
        finally:
            self._active = False
        return False


def scan_orphan_archives(
    *,
    archive_dir: os.PathLike[str] | str,
    manifest_relative_paths: Collection[str],
    now: datetime,
) -> OrphanScanResult:
    """Delete final archive files older than one hour without a manifest."""

    selected_now = _aware_utc(now, field_name="now")
    if isinstance(manifest_relative_paths, (str, bytes, bytearray)):
        raise TypeError("manifest_relative_paths must be a collection of paths")
    known_paths = set()
    for relative_path in manifest_relative_paths:
        _relative_parts(relative_path)
        known_paths.add(relative_path)
    root = _archive_root(archive_dir, create=False)
    if not root.exists():
        return OrphanScanResult((), ())
    cutoff = (selected_now - _ORPHAN_MINIMUM_AGE).timestamp()
    deleted: list[str] = []
    failures: list[ArchiveCleanupErrorCode] = []
    for candidate in sorted(root.rglob(f"*{_ARCHIVE_SUFFIX}")):
        try:
            resolved = candidate.resolve(strict=False)
            if not resolved.is_relative_to(root):
                failures.append(ArchiveCleanupErrorCode.INVALID_PATH)
                continue
            relative_path = candidate.relative_to(root).as_posix()
            if relative_path in known_paths or candidate.stat().st_mtime >= cutoff:
                continue
            candidate.unlink()
            deleted.append(relative_path)
        except FileNotFoundError:
            continue
        except OSError:
            failures.append(ArchiveCleanupErrorCode.DELETE_IO_FAILED)
    return OrphanScanResult(tuple(deleted), tuple(failures))


def cleanup_expired_archives(
    db: Session,
    *,
    archive_dir: os.PathLike[str] | str,
    now: datetime,
    audit_missing: Callable[[int, ArchiveAuditCode], None],
    enqueue_retry: Callable[[int, ArchiveCleanupErrorCode], None],
) -> ArchiveCleanupResult:
    """Stage retention state only after each expired archive is absent on disk."""

    if not isinstance(db, Session):
        raise TypeError("db must be a SQLAlchemy Session")
    if not callable(audit_missing) or not callable(enqueue_retry):
        raise TypeError("archive maintenance callbacks must be callable")
    selected_now = _aware_utc(now, field_name="now")
    root = _archive_root(archive_dir, create=False)
    manifests = db.scalars(
        select(IntegrationArchiveManifest)
        .where(
            IntegrationArchiveManifest.expires_at < selected_now,
            IntegrationArchiveManifest.deleted_at.is_(None),
        )
        .order_by(IntegrationArchiveManifest.id)
    ).all()
    deleted_count = 0
    missing_count = 0
    retry_count = 0
    for manifest in manifests:
        try:
            file_path = _contained_path(root, manifest.relative_path)
        except ValueError:
            enqueue_retry(manifest.id, ArchiveCleanupErrorCode.INVALID_PATH)
            retry_count += 1
            continue
        try:
            file_path.unlink()
        except FileNotFoundError:
            audit_missing(manifest.id, ArchiveAuditCode.FILE_MISSING)
            manifest.deleted_at = selected_now
            missing_count += 1
        except OSError:
            enqueue_retry(
                manifest.id,
                ArchiveCleanupErrorCode.DELETE_IO_FAILED,
            )
            retry_count += 1
        else:
            manifest.deleted_at = selected_now
            deleted_count += 1
    return ArchiveCleanupResult(
        deleted_count=deleted_count,
        missing_count=missing_count,
        retry_count=retry_count,
    )


__all__ = [
    "ARCHIVE_ENVELOPE_PREFIX",
    "ArchiveArtifact",
    "ArchiveAuditCode",
    "ArchiveCleanupErrorCode",
    "ArchiveCleanupResult",
    "ArchiveDecryptionError",
    "ArchivePage",
    "ArchiveWriteError",
    "OrphanScanResult",
    "archive_expires_at",
    "cleanup_expired_archives",
    "create_archive_page",
    "decrypt_archive_bytes",
    "scan_orphan_archives",
]
