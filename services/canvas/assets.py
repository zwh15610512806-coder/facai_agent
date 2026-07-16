"""Transactional image-asset persistence with filesystem rollback semantics."""
from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from PIL import Image, ImageOps
from sqlalchemy import event, inspect as sqlalchemy_inspect, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from canvas_models import (
    CanvasAsset,
    CanvasAssetOperation,
    CanvasGenerationAttempt,
    CanvasGenerationItem,
    CanvasGenerationItemInput,
    CanvasProject,
)
from services.canvas import storage
from services.canvas.image_validation import (
    CanvasImageValidationError,
    InspectedImage,
    _inspect_image_with_loaded_pixels,
    inspect_image,
    inspect_trusted_image,
)


WORKING_PROCESSOR_VERSION = "canvas-working-v1"
_LEDGER_KEY = "canvas_file_rollback_ledger"
_LEDGER_HOOK_KEY = "canvas_file_rollback_hooks_installed"
_RETRY_KEY = "canvas_file_cleanup_retry"
_DB_ROOT_MATERIALIZED_KEY = "canvas_database_root_materialized"
_DERIVED_ASSET_TYPES = {
    "working",
    "preview",
    "cutout",
    "generated_background",
    "composed",
    "export",
}
_ALLOCATION_LOCK = storage.CANVAS_ALLOCATION_LOCK


def _generation_reservations(db: Session, *, project_id: str) -> tuple[int, int]:
    # Use a fresh read Session after acquiring the shared allocation lock. The
    # caller's transaction may have read project state before waiting for a
    # concurrent Generation reservation and therefore hold an older snapshot.
    from services.canvas.generation.repository import active_generation_reservations

    with Session(bind=db.get_bind()) as reservation_db:
        return active_generation_reservations(
            reservation_db,
            project_id=project_id,
        )


def collect_generation_asset_references(
    db: Session,
    *,
    project_id: str,
    asset_id: str,
) -> set[str]:
    """Return durable Generation references that block asset soft deletion.

    The asset id is globally unique, so references are intentionally collected
    across projects to fail safe if legacy or manually edited data is corrupt.
    ``project_id`` remains part of the caller contract for scoped asset lookup.
    """

    _ = project_id

    references: set[str] = set()
    item_rows = db.execute(
        select(
            CanvasGenerationItem.latest_background_asset_id,
            CanvasGenerationItem.latest_composed_asset_id,
        )
        .where(
            or_(
                CanvasGenerationItem.latest_background_asset_id == asset_id,
                CanvasGenerationItem.latest_composed_asset_id == asset_id,
            ),
        )
    ).all()
    if any(row.latest_background_asset_id == asset_id for row in item_rows):
        references.add("generationItemBackground")
    if any(row.latest_composed_asset_id == asset_id for row in item_rows):
        references.add("generationItemComposed")

    if db.scalar(
        select(CanvasGenerationItemInput.id)
        .join(
            CanvasGenerationItem,
            CanvasGenerationItem.id == CanvasGenerationItemInput.item_id,
        )
        .where(
            CanvasGenerationItemInput.asset_id == asset_id,
        )
        .limit(1)
    ) is not None:
        references.add("generationInput")

    attempt_rows = db.execute(
        select(
            CanvasGenerationAttempt.background_asset_id,
            CanvasGenerationAttempt.background_preview_asset_id,
            CanvasGenerationAttempt.composed_asset_id,
            CanvasGenerationAttempt.composed_preview_asset_id,
        )
        .join(
            CanvasGenerationItem,
            CanvasGenerationItem.id == CanvasGenerationAttempt.item_id,
        )
        .where(
            or_(
                CanvasGenerationAttempt.background_asset_id == asset_id,
                CanvasGenerationAttempt.background_preview_asset_id == asset_id,
                CanvasGenerationAttempt.composed_asset_id == asset_id,
                CanvasGenerationAttempt.composed_preview_asset_id == asset_id,
            ),
        )
    ).all()
    labels = (
        ("background_asset_id", "generationAttemptBackground"),
        ("background_preview_asset_id", "generationAttemptBackgroundPreview"),
        ("composed_asset_id", "generationAttemptComposed"),
        ("composed_preview_asset_id", "generationAttemptComposedPreview"),
    )
    for attribute, label in labels:
        if any(getattr(row, attribute) == asset_id for row in attempt_rows):
            references.add(label)
    return references


def collect_export_asset_references(
    db: Session,
    *,
    project_id: str,
    asset_id: str,
) -> set[str]:
    """Protect every selected composed version captured by an export request."""

    references: set[str] = set()
    snapshots = db.scalars(
        select(CanvasAssetOperation.request_snapshot_json).where(
            CanvasAssetOperation.project_id == project_id,
            CanvasAssetOperation.operation_type == "export",
        )
    ).all()
    for raw in snapshots:
        try:
            snapshot = json.loads(raw)
        except (TypeError, ValueError):
            continue
        selections = snapshot.get("selectedBoards") if isinstance(snapshot, dict) else None
        if not isinstance(selections, list):
            continue
        if any(
            isinstance(selection, dict)
            and selection.get("composedAssetId") == asset_id
            for selection in selections
        ):
            references.add("exportSelection")
            break
    return references
_GLOBAL_CLEANUP_LOCK = threading.RLock()
_GLOBAL_CLEANUP_RETRY: set["_OwnedFile"] = set()


class CanvasAssetPersistenceError(storage.CanvasStorageError):
    """Stable persistence failure for later HTTP adapters."""


class _SavepointCommittedListenerError(Exception):
    """A listener failed after the persistence SAVEPOINT had committed."""


@dataclass(frozen=True)
class UploadedAssetSet:
    source: CanvasAsset
    working: CanvasAsset


@dataclass(frozen=True)
class _OwnedFile:
    path: Path
    data_root: Path
    device: int
    inode: int
    byte_count: int | None = None
    sha256: str | None = None
    native_identity: tuple[object, object] | None = None


def _asset_error(code: str, message: str) -> CanvasAssetPersistenceError:
    return CanvasAssetPersistenceError(code, message)


def _wrap_error(exc: storage.CanvasStorageError) -> CanvasAssetPersistenceError:
    if isinstance(exc, CanvasAssetPersistenceError):
        return exc
    return _asset_error(exc.code, str(exc))


def _owned_pinned_file(
    path: Path,
    *,
    data_root: Path,
    pin: storage._PinnedEntry,
    byte_count: int | None,
    sha256: str | None,
) -> _OwnedFile:
    return _OwnedFile(
        path=path,
        data_root=data_root,
        device=int(pin.identity[0]) if isinstance(pin.identity[0], int) else 0,
        inode=pin.legacy_file_id,
        byte_count=byte_count,
        sha256=sha256,
        native_identity=pin.identity,
    )


def _delete_owned_file(owned_file: _OwnedFile) -> bool:
    """Delete only the exact owned inode through one verified native handle."""
    try:
        storage._require_contained(owned_file.path, owned_file.data_root)
        if not storage._lexists(owned_file.path.parent):
            return True
        with storage._pin_directory_chain(owned_file.path.parent) as parent_chain:
            parent = parent_chain[-1]
            records = storage._directory_records(
                parent,
                max_entries=storage.CANVAS_MAX_TREE_ENTRIES,
            )
            record = next(
                (record for record in records if record.name == owned_file.path.name),
                None,
            )
            if record is None:
                return True
            if record.is_directory or record.attributes & getattr(
                storage.stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                0x400,
            ):
                return True
            if record.file_id != owned_file.inode:
                return True
            pin = storage._open_record(parent, record, delete=True)
            try:
                if (
                    owned_file.native_identity is not None
                    and pin.identity != owned_file.native_identity
                ):
                    return True
                digest, byte_count = storage._pinned_file_sha256(pin)
                if owned_file.byte_count is not None and byte_count != owned_file.byte_count:
                    return True
                if owned_file.sha256 is not None and digest != owned_file.sha256:
                    return True
                storage._dispose_pinned_entry(pin)
                return True
            finally:
                if not pin.closed:
                    pin.close()
    except (OSError, storage.CanvasStorageError):
        return False


def _cleanup_owned_files(
    owned_files: set[_OwnedFile] | list[_OwnedFile],
) -> set[_OwnedFile]:
    remaining: set[_OwnedFile] = set()
    for owned_file in tuple(owned_files):
        try:
            deleted = _delete_owned_file(owned_file)
        except Exception:
            deleted = False
        if not deleted:
            remaining.add(owned_file)
    return remaining


def _queue_cleanup_retry(db: Session, owned_files: set[_OwnedFile]) -> None:
    if owned_files:
        db.info.setdefault(_RETRY_KEY, set()).update(owned_files)
        with _GLOBAL_CLEANUP_LOCK:
            _GLOBAL_CLEANUP_RETRY.update(owned_files)


def retry_pending_file_cleanup(db: Session) -> int:
    """Retry identity-safe cleanup and retain every still-failing owned file."""
    session_pending: set[_OwnedFile] = set(db.info.get(_RETRY_KEY, set()))
    with _GLOBAL_CLEANUP_LOCK:
        pending = set(_GLOBAL_CLEANUP_RETRY)
        pending.update(session_pending)
        if not pending:
            db.info.pop(_RETRY_KEY, None)
            return 0
        _GLOBAL_CLEANUP_RETRY.difference_update(pending)
    remaining = _cleanup_owned_files(pending)
    with _GLOBAL_CLEANUP_LOCK:
        _GLOBAL_CLEANUP_RETRY.update(remaining)
    if remaining:
        db.info[_RETRY_KEY] = remaining
    else:
        db.info.pop(_RETRY_KEY, None)
    return len(remaining)


def _is_transaction_descendant(transaction: Any, ancestor: Any) -> bool:
    current = transaction
    while current is not None:
        if current is ancestor:
            return True
        current = getattr(current, "_parent", None)
    return False


def _discard_empty_ledger(db: Session) -> None:
    ledger = db.info.get(_LEDGER_KEY)
    if not ledger:
        db.info.pop(_LEDGER_KEY, None)


def _after_commit(db: Session) -> None:
    retry_pending_file_cleanup(db)
    ledger: dict[Any, set[_OwnedFile]] | None = db.info.get(_LEDGER_KEY)
    if not ledger:
        return
    if db.in_nested_transaction():
        transaction = db.get_nested_transaction()
        if transaction is None:
            return
        owned_files = ledger.pop(transaction, set())
        parent = getattr(transaction, "_parent", None)
        if parent is not None and owned_files:
            ledger.setdefault(parent, set()).update(owned_files)
    else:
        ledger.clear()
    _discard_empty_ledger(db)


def _after_soft_rollback(db: Session, previous_transaction: Any) -> None:
    retry_pending_file_cleanup(db)
    ledger: dict[Any, set[_OwnedFile]] | None = db.info.get(_LEDGER_KEY)
    if not ledger:
        return
    rollback_files: set[_OwnedFile] = set()
    for transaction in tuple(ledger):
        if _is_transaction_descendant(transaction, previous_transaction):
            rollback_files.update(ledger.pop(transaction, set()))
    _queue_cleanup_retry(db, _cleanup_owned_files(rollback_files))
    _discard_empty_ledger(db)
    retry_pending_file_cleanup(db)


def _after_transaction_end(db: Session, transaction: Any) -> None:
    retry_pending_file_cleanup(db)
    if db.info.get(_DB_ROOT_MATERIALIZED_KEY) is transaction:
        db.info.pop(_DB_ROOT_MATERIALIZED_KEY, None)
    ledger: dict[Any, set[_OwnedFile]] | None = db.info.get(_LEDGER_KEY)
    if not ledger:
        return
    _queue_cleanup_retry(
        db,
        _cleanup_owned_files(ledger.pop(transaction, set())),
    )
    _discard_empty_ledger(db)
    retry_pending_file_cleanup(db)


def _ensure_ledger_hooks(db: Session) -> None:
    retry_pending_file_cleanup(db)
    if db.info.get(_LEDGER_HOOK_KEY):
        return
    event.listen(db, "after_commit", _after_commit, insert=True)
    event.listen(db, "after_soft_rollback", _after_soft_rollback, insert=True)
    event.listen(db, "after_transaction_end", _after_transaction_end, insert=True)
    db.info[_LEDGER_HOOK_KEY] = True


def _current_transaction(db: Session) -> Any:
    transaction = db.get_nested_transaction() or db.get_transaction()
    if transaction is None:
        db.begin()
        transaction = db.get_transaction()
    if transaction is None:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset transaction could not be started",
        )
    return transaction


def _ensure_database_root_transaction(db: Session) -> None:
    """Materialize SQLite's DBAPI BEGIN before creating a SAVEPOINT."""
    root_transaction = db.get_transaction()
    if root_transaction is None:
        db.begin()
        root_transaction = db.get_transaction()
    if root_transaction is None:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset root transaction could not be started",
        )
    connection = root_transaction.connection(db.get_bind())
    if connection.dialect.name != "sqlite":
        return
    if (
        connection.in_nested_transaction()
        and db.info.get(_DB_ROOT_MATERIALIZED_KEY) is not root_transaction
    ):
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset transaction nesting is unsafe",
        )
    driver_connection = getattr(connection.connection, "driver_connection", None)
    if driver_connection is not None and not getattr(
        driver_connection,
        "in_transaction",
        True,
    ):
        # Capacity-changing asset writes must enter SQLite's writer queue
        # before reading project state. A deferred BEGIN lets a second writer
        # hold a read snapshot while the first commits, producing a lock
        # inversion and stale reservation view.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    db.info[_DB_ROOT_MATERIALIZED_KEY] = root_transaction


def _register_owned_file(db: Session, owned_file: _OwnedFile) -> None:
    _ensure_ledger_hooks(db)
    transaction = _current_transaction(db)
    ledger: dict[Any, set[_OwnedFile]] = db.info.setdefault(_LEDGER_KEY, {})
    ledger.setdefault(transaction, set()).add(owned_file)


def _rollback_failed_persistence(
    db: Session,
    savepoint: Any,
    owned_files: list[_OwnedFile],
) -> None:
    try:
        state_name = getattr(getattr(savepoint, "_state", None), "name", None)
        if savepoint is not None and state_name not in {"COMMITTED", "CLOSED"}:
            try:
                savepoint.rollback()
            except Exception:
                pass
    finally:
        _queue_cleanup_retry(db, _cleanup_owned_files(owned_files))
        retry_pending_file_cleanup(db)


def _commit_persistence_savepoint(savepoint: Any) -> None:
    try:
        savepoint.commit()
    except Exception as exc:
        state_name = getattr(getattr(savepoint, "_state", None), "name", None)
        if state_name not in {"COMMITTED", "CLOSED"}:
            raise
        if state_name == "COMMITTED":
            try:
                savepoint.close()
            except Exception:
                pass
        raise _SavepointCommittedListenerError from exc


def _serialize_metadata(metadata: dict[str, Any]) -> str:
    if type(metadata) is not dict:
        raise _asset_error(
            "canvas_asset_metadata_invalid",
            "canvas asset metadata must be an object",
        )
    try:
        return json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise _asset_error(
            "canvas_asset_metadata_invalid",
            "canvas asset metadata must be finite JSON",
        ) from exc


def _safe_original_filename(filename: object) -> str:
    if not isinstance(filename, str):
        raise _asset_error(
            "canvas_asset_filename_invalid",
            "canvas asset filename is invalid",
        )
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not basename or "\x00" in basename or len(basename) > 500:
        raise _asset_error(
            "canvas_asset_filename_invalid",
            "canvas asset filename is invalid",
        )
    return basename


def _inspect(
    data: bytes,
    *,
    filename: str,
    declared_mime: str,
    trusted: bool = False,
) -> InspectedImage:
    try:
        inspector = inspect_trusted_image if trusted else inspect_image
        return inspector(
            data,
            filename=filename,
            declared_mime=declared_mime,
        )
    except CanvasImageValidationError as exc:
        raise _asset_error(exc.code, str(exc)) from exc


def _inspect_upload_with_loaded_pixels(
    data: bytes,
    *,
    filename: str,
    declared_mime: str,
) -> tuple[InspectedImage, Image.Image]:
    try:
        return _inspect_image_with_loaded_pixels(
            data,
            filename=filename,
            declared_mime=declared_mime,
        )
    except CanvasImageValidationError as exc:
        raise _asset_error(exc.code, str(exc)) from exc


def _require_project(db: Session, project_id: str) -> CanvasProject:
    try:
        with db.no_autoflush:
            row = db.execute(
                select(CanvasProject, CanvasProject.status).where(
                    CanvasProject.id == project_id
                )
            ).one_or_none()
    except Exception as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas project lookup failed",
        ) from exc
    if row is None:
        raise _asset_error(
            "canvas_asset_project_not_found",
            "canvas project does not exist",
        )
    project, database_status = row
    project_state = sqlalchemy_inspect(project)
    if project in db.deleted or project_state.deleted:
        effective_status = "deleting"
    elif project_state.attrs.status.history.has_changes():
        effective_status = project.status
    else:
        set_committed_value(project, "status", database_status)
        effective_status = database_status
    if effective_status != "active":
        raise _asset_error(
            "canvas_asset_project_inactive",
            "canvas project is not active",
        )
    return project


def _require_parent_asset(
    db: Session,
    *,
    project_id: str,
    source_asset_id: str,
) -> CanvasAsset:
    try:
        with db.no_autoflush:
            row = db.execute(
                select(
                    CanvasAsset,
                    CanvasAsset.deleted_at,
                    CanvasAsset.project_id,
                ).where(CanvasAsset.id == source_asset_id)
            ).one_or_none()
    except Exception as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas source asset lookup failed",
        ) from exc
    if row is None:
        raise _asset_error(
            "canvas_asset_source_not_found",
            "source asset does not exist",
        )
    parent, database_deleted_at, database_project_id = row
    parent_state = sqlalchemy_inspect(parent)
    if parent in db.deleted or parent_state.deleted:
        effective_deleted_at = True
    elif parent_state.attrs.deleted_at.history.has_changes():
        effective_deleted_at = parent.deleted_at
    else:
        set_committed_value(parent, "deleted_at", database_deleted_at)
        effective_deleted_at = database_deleted_at
    if effective_deleted_at is not None:
        raise _asset_error(
            "canvas_asset_source_deleted",
            "source asset is deleted",
        )
    if parent_state.attrs.project_id.history.has_changes():
        effective_project_id = parent.project_id
    else:
        set_committed_value(parent, "project_id", database_project_id)
        effective_project_id = database_project_id
    if effective_project_id != project_id:
        raise _asset_error(
            "canvas_asset_source_project_mismatch",
            "source asset belongs to another project",
        )
    try:
        storage.resolve_asset_path(parent, project_id=project_id)
    except storage.CanvasStorageError as exc:
        raise _wrap_error(exc) from exc
    return parent


def _canonical_working_png(source: Image.Image) -> tuple[bytes, str, bool]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with source:
                orientation = source.getexif().get(274, 1)
                transposed = ImageOps.exif_transpose(source)
                has_alpha = "A" in transposed.getbands() or "transparency" in transposed.info
                canonical_mode = "RGBA" if has_alpha else "RGB"
                canonical = transposed.convert(canonical_mode)
                canonical.info.clear()
                canonical.load()
                output = io.BytesIO()
                canonical.save(
                    output,
                    format="PNG",
                    optimize=False,
                    compress_level=9,
                )
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise _asset_error(
            "canvas_image_decompression_bomb",
            "image triggered Pillow decompression-bomb protection",
        ) from exc
    except CanvasAssetPersistenceError:
        raise
    except Exception as exc:
        raise _asset_error(
            "canvas_image_decode_failed",
            "image could not be converted to a working asset",
        ) from exc
    return output.getvalue(), canonical_mode, orientation in (2, 3, 4, 5, 6, 7, 8)


def _assert_destination_available(destination: Path, *, data_root: Path) -> None:
    storage._assert_safe_path(destination.parent, root=data_root, must_exist=True, expected_kind="directory")
    storage._assert_safe_path(destination, root=data_root)
    if storage._lexists(destination):
        raise _asset_error(
            "canvas_storage_collision",
            "canvas asset UUID already exists",
        )


def _atomic_write(
    *,
    root: Path,
    destination: Path,
    data: bytes,
    ownership: list[_OwnedFile],
) -> _OwnedFile:
    data_root = storage._data_root()
    temporary = root / "tmp" / f"{destination.stem}.uploading"
    storage._require_contained(temporary, data_root)
    storage._require_contained(destination, data_root)
    expected_sha256 = hashlib.sha256(data).hexdigest()
    file_pin: storage._PinnedEntry | None = None
    temporary_owned: _OwnedFile | None = None
    provisional_owned: _OwnedFile | None = None
    try:
        with (
            storage._pin_directory_chain(
                root / "tmp",
                writable_final=True,
            ) as temporary_chain,
            storage._pin_directory_chain(
                destination.parent,
                writable_final=True,
            ) as destination_chain,
        ):
            temporary_parent = temporary_chain[-1]
            destination_parent = destination_chain[-1]
            file_pin = storage._create_pinned_file(
                temporary_parent,
                temporary.name,
            )
            temporary_owned = _owned_pinned_file(
                temporary,
                data_root=data_root,
                pin=file_pin,
                byte_count=None,
                sha256=None,
            )
            ownership.append(temporary_owned)
            storage._write_pinned_file(file_pin, data)
            storage._flush_pinned_file(file_pin)
            written_sha256, written_bytes = storage._pinned_file_sha256(file_pin)
            if written_bytes != len(data) or written_sha256 != expected_sha256:
                raise _asset_error(
                    "canvas_storage_atomic_write_failed",
                    "canvas temporary file verification failed",
                )
            ownership.remove(temporary_owned)
            temporary_owned = _owned_pinned_file(
                temporary,
                data_root=data_root,
                pin=file_pin,
                byte_count=len(data),
                sha256=expected_sha256,
            )
            ownership.append(temporary_owned)

            provisional_owned = _owned_pinned_file(
                destination,
                data_root=data_root,
                pin=file_pin,
                byte_count=len(data),
                sha256=expected_sha256,
            )
            ownership.append(provisional_owned)
            storage._rename_pinned_file_no_replace(
                file_pin,
                destination_parent,
                destination.name,
            )
            ownership.remove(temporary_owned)
            temporary_owned = None

            published_pin = storage._open_published_file_verifier(
                destination_parent,
                destination.name,
            )
            try:
                if published_pin.identity != file_pin.identity:
                    raise _asset_error(
                        "canvas_storage_atomic_write_failed",
                        "canvas published file identity changed",
                    )
            finally:
                published_pin.close()

            published_sha256, published_bytes = storage._pinned_file_sha256(file_pin)
            if published_bytes != len(data) or published_sha256 != expected_sha256:
                raise _asset_error(
                    "canvas_storage_atomic_write_failed",
                    "canvas published file verification failed",
                )
            for directory_pin in (temporary_parent, destination_parent):
                (
                    identity,
                    legacy_file_id,
                    attributes,
                    _,
                    _,
                    is_directory,
                ) = storage._current_entry_metadata(directory_pin)
                if (
                    identity != directory_pin.identity
                    or legacy_file_id != directory_pin.legacy_file_id
                    or attributes != directory_pin.attributes
                    or not is_directory
                ):
                    raise _asset_error(
                        "canvas_storage_atomic_write_failed",
                        "canvas publish directory changed",
                    )
            file_pin.close()
            file_pin = None
            return provisional_owned
    except CanvasAssetPersistenceError:
        raise
    except storage.CanvasStorageError as exc:
        raise _wrap_error(exc) from exc
    except OSError as exc:
        raise _asset_error(
            "canvas_storage_atomic_write_failed",
            "canvas asset atomic write failed",
        ) from exc
    finally:
        if file_pin is not None and not file_pin.closed:
            disposed = False
            try:
                storage._dispose_pinned_entry(file_pin)
                disposed = True
            except storage.CanvasStorageError:
                try:
                    file_pin.close()
                except storage.CanvasStorageError:
                    pass
            if disposed:
                for owned_file in (temporary_owned, provisional_owned):
                    if owned_file is not None and owned_file in ownership:
                        ownership.remove(owned_file)


def _new_asset(
    *,
    asset_id: str,
    project_id: str,
    asset_type: str,
    relative_path: str,
    original_filename: str,
    inspected: InspectedImage,
    source_asset_id: str | None,
    metadata_json: str,
    processor_version: str | None = None,
) -> CanvasAsset:
    return CanvasAsset(
        id=asset_id,
        project_id=project_id,
        asset_type=asset_type,
        relative_path=relative_path,
        original_filename=original_filename,
        mime_type=inspected.mime_type,
        byte_count=0,
        width=inspected.width,
        height=inspected.height,
        sha256=inspected.sha256,
        source_asset_id=source_asset_id,
        transparency_status="unknown",
        processor_version=processor_version,
        metadata_json=metadata_json,
    )


def persist_uploaded_source(
    db: Session,
    *,
    project_id: str,
    filename: str,
    declared_mime: str,
    data: bytes,
) -> UploadedAssetSet:
    """Persist immutable source bytes plus one deterministic working PNG."""
    original_filename = _safe_original_filename(filename)
    inspected_source, loaded_source = _inspect_upload_with_loaded_pixels(
        data,
        filename=original_filename,
        declared_mime=declared_mime,
    )
    working_data, canonical_mode, exif_transposed = _canonical_working_png(loaded_source)
    inspected_working = _inspect(
        working_data,
        filename="working.png",
        declared_mime="image/png",
        trusted=True,
    )
    _ensure_ledger_hooks(db)
    try:
        _ensure_database_root_transaction(db)
    except Exception as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset transaction could not be started",
        ) from exc
    _require_project(db, project_id)
    try:
        savepoint = db.begin_nested()
    except Exception as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset savepoint could not be started",
        ) from exc

    source_id = str(uuid4())
    working_id = str(uuid4())
    source_extension = Path(original_filename).suffix.lower()
    owned_files: list[_OwnedFile] = []
    _ALLOCATION_LOCK.acquire()
    try:
        root = storage.ensure_project_tree(project_id)
        reserved_project, reserved_total = _generation_reservations(
            db,
            project_id=project_id,
        )
        storage.assert_canvas_capacity(
            project_id=project_id,
            additional_bytes=len(data) + len(working_data),
            reserved_project_bytes=reserved_project,
            reserved_total_bytes=reserved_total,
        )
        source_destination = root / "source" / f"{source_id}{source_extension}"
        source_owned = _atomic_write(
            root=root,
            destination=source_destination,
            data=data,
            ownership=owned_files,
        )
        _register_owned_file(db, source_owned)

        storage.assert_canvas_capacity(
            project_id=project_id,
            additional_bytes=len(working_data),
            reserved_project_bytes=reserved_project,
            reserved_total_bytes=reserved_total,
        )
        working_destination = root / "working" / f"{working_id}.png"
        working_owned = _atomic_write(
            root=root,
            destination=working_destination,
            data=working_data,
            ownership=owned_files,
        )
        _register_owned_file(db, working_owned)

        source_asset = _new_asset(
            asset_id=source_id,
            project_id=project_id,
            asset_type="source",
            relative_path=f"source/{source_id}{source_extension}",
            original_filename=original_filename,
            inspected=inspected_source,
            source_asset_id=None,
            metadata_json=_serialize_metadata(
                {
                    "format": inspected_source.format,
                    "has_alpha": inspected_source.has_alpha,
                }
            ),
        )
        source_asset.byte_count = len(data)
        working_asset = _new_asset(
            asset_id=working_id,
            project_id=project_id,
            asset_type="working",
            relative_path=f"working/{working_id}.png",
            original_filename=original_filename,
            inspected=inspected_working,
            source_asset_id=source_id,
            metadata_json=_serialize_metadata(
                {
                    "canonical_mode": canonical_mode,
                    "exif_transposed": exif_transposed,
                    "source_format": inspected_source.format,
                }
            ),
            processor_version=WORKING_PROCESSOR_VERSION,
        )
        working_asset.byte_count = len(working_data)
        db.add_all([source_asset, working_asset])
        db.flush()
        _commit_persistence_savepoint(savepoint)
        return UploadedAssetSet(source=source_asset, working=working_asset)
    except _SavepointCommittedListenerError as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset savepoint completion listener failed",
        ) from exc
    except CanvasAssetPersistenceError:
        _rollback_failed_persistence(db, savepoint, owned_files)
        raise
    except storage.CanvasStorageError as exc:
        _rollback_failed_persistence(db, savepoint, owned_files)
        raise _wrap_error(exc) from exc
    except Exception as exc:
        _rollback_failed_persistence(db, savepoint, owned_files)
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset database flush failed",
        ) from exc
    finally:
        _ALLOCATION_LOCK.release()


def read_verified_asset_bytes(
    db: Session,
    *,
    asset: CanvasAsset,
    project_id: str | None = None,
) -> bytes:
    """Read one live asset through a pinned handle and verify its persisted digest."""

    asset_id = getattr(asset, "id", None)
    if not isinstance(asset_id, str):
        raise _asset_error("canvas_storage_asset_missing", "canvas asset file is missing")
    statement = select(
        CanvasAsset.id,
        CanvasAsset.project_id,
        CanvasAsset.asset_type,
        CanvasAsset.relative_path,
        CanvasAsset.mime_type,
        CanvasAsset.byte_count,
        CanvasAsset.sha256,
        CanvasAsset.deleted_at,
    ).where(CanvasAsset.id == asset_id)
    if project_id is not None:
        statement = statement.where(CanvasAsset.project_id == project_id)
    try:
        with db.no_autoflush:
            record = db.execute(statement).mappings().one_or_none()
    except Exception as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset lookup failed",
        ) from exc
    if record is None:
        raise _asset_error("canvas_storage_asset_missing", "canvas asset file is missing")
    if record["deleted_at"] is not None:
        raise _asset_error("canvas_storage_asset_deleted", "canvas asset is deleted")

    path_record = SimpleNamespace(**dict(record))
    path = storage.resolve_asset_path(path_record, project_id=record["project_id"])
    try:
        with storage._pin_directory_chain(path.parent) as parent_chain:
            parent = parent_chain[-1]
            records = storage._directory_records(
                parent,
                max_entries=storage.CANVAS_MAX_TREE_ENTRIES,
            )
            file_record = next((item for item in records if item.name == path.name), None)
            if file_record is None:
                storage._reject("canvas_storage_asset_missing", "canvas asset file is missing")
            if file_record.is_directory or file_record.attributes & getattr(
                storage.stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                0x400,
            ):
                storage._reject(
                    "canvas_storage_unsafe_entry",
                    "canvas asset is not a regular file",
                )
            pin = storage._open_record(parent, file_record)
            try:
                storage._refresh_pinned_file(pin)
                if pin.byte_count != record["byte_count"]:
                    storage._reject(
                        "canvas_storage_unsafe_entry",
                        "canvas asset file changed",
                    )
                data = storage._pinned_file_bytes(pin)
            finally:
                pin.close()
    except storage.CanvasStorageError:
        raise
    except OSError as exc:
        raise _asset_error(
            "canvas_storage_io_failed",
            "canvas asset file could not be read",
        ) from exc
    if (
        len(data) != record["byte_count"]
        or hashlib.sha256(data).hexdigest() != record["sha256"]
    ):
        raise _asset_error(
            "canvas_storage_unsafe_entry",
            "canvas asset content changed",
        )
    return data


def persist_derived_image(
    db: Session,
    *,
    project_id: str,
    asset_type: str,
    data: bytes,
    mime_type: str,
    source_asset_id: str | None,
    metadata: dict,
    processor_version: str | None = None,
    generation_id: str | None = None,
) -> CanvasAsset:
    """Persist one trusted PNG derivative without committing the caller Session."""
    if asset_type not in _DERIVED_ASSET_TYPES:
        raise _asset_error("canvas_asset_type_invalid", "asset type is not derived")
    if mime_type != "image/png":
        raise _asset_error(
            "canvas_asset_derived_format_invalid",
            "derived image assets must currently be PNG",
        )
    metadata_json = _serialize_metadata(metadata)
    inspected = _inspect(
        data,
        filename=f"{asset_type}.png",
        declared_mime=mime_type,
        trusted=True,
    )
    if asset_type == "working" and source_asset_id is None:
        raise _asset_error(
            "canvas_asset_source_not_found",
            "working assets require a source parent",
        )
    _ensure_ledger_hooks(db)
    try:
        _ensure_database_root_transaction(db)
    except Exception as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset transaction could not be started",
        ) from exc
    _require_project(db, project_id)
    if source_asset_id is not None:
        _require_parent_asset(
            db,
            project_id=project_id,
            source_asset_id=source_asset_id,
        )
    try:
        savepoint = db.begin_nested()
    except Exception as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset savepoint could not be started",
        ) from exc

    asset_id = str(uuid4())
    owned_files: list[_OwnedFile] = []
    _ALLOCATION_LOCK.acquire()
    try:
        root = storage.ensure_project_tree(project_id)
        reserved_project, reserved_total = _generation_reservations(
            db,
            project_id=project_id,
        )
        storage.assert_canvas_capacity(
            project_id=project_id,
            # A Generation allocation is already represented by its remaining
            # reservation. Debit the newly published bytes in the same DB
            # savepoint instead of counting them twice.
            additional_bytes=0 if generation_id is not None else len(data),
            reserved_project_bytes=reserved_project,
            reserved_total_bytes=reserved_total,
        )
        directory = storage.ASSET_TYPE_DIRECTORIES[asset_type]
        destination = root / directory / f"{asset_id}.png"
        owned_file = _atomic_write(
            root=root,
            destination=destination,
            data=data,
            ownership=owned_files,
        )
        _register_owned_file(db, owned_file)

        asset = _new_asset(
            asset_id=asset_id,
            project_id=project_id,
            asset_type=asset_type,
            relative_path=f"{directory}/{asset_id}.png",
            original_filename=f"{asset_type}.png",
            inspected=inspected,
            source_asset_id=source_asset_id,
            metadata_json=metadata_json,
            processor_version=processor_version,
        )
        asset.byte_count = len(data)
        db.add(asset)
        if generation_id is not None:
            from services.canvas.generation.repository import (
                debit_generation_reservation,
            )

            debit_generation_reservation(
                db,
                generation_id=generation_id,
                allocated_bytes=len(data),
                project_id=project_id,
            )
        db.flush()
        _commit_persistence_savepoint(savepoint)
        return asset
    except _SavepointCommittedListenerError as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset savepoint completion listener failed",
        ) from exc
    except CanvasAssetPersistenceError:
        _rollback_failed_persistence(db, savepoint, owned_files)
        raise
    except storage.CanvasStorageError as exc:
        _rollback_failed_persistence(db, savepoint, owned_files)
        raise _wrap_error(exc) from exc
    except Exception as exc:
        _rollback_failed_persistence(db, savepoint, owned_files)
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset database flush failed",
        ) from exc
    finally:
        _ALLOCATION_LOCK.release()


def persist_export_file(
    db: Session,
    *,
    project_id: str,
    data: bytes,
    mime_type: str,
    original_filename: str,
    source_asset_id: str,
    width: int,
    height: int,
    metadata: dict[str, Any],
    processor_version: str,
) -> CanvasAsset:
    """Persist one authoritative image or ZIP export transactionally."""

    formats = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "application/zip": ".zip",
    }
    extension = formats.get(mime_type)
    if extension is None or not isinstance(data, bytes) or not data:
        raise _asset_error(
            "canvas_asset_derived_format_invalid",
            "export file format is invalid",
        )
    filename = _safe_original_filename(original_filename)
    if not filename.casefold().endswith(extension):
        raise _asset_error(
            "canvas_asset_filename_invalid",
            "export filename does not match its format",
        )
    if mime_type == "application/zip":
        if width != 0 or height != 0:
            raise _asset_error(
                "canvas_asset_dimensions_invalid",
                "ZIP exports cannot have image dimensions",
            )
    else:
        inspected = _inspect(
            data,
            filename=filename,
            declared_mime=mime_type,
            trusted=True,
        )
        if (inspected.width, inspected.height) != (width, height):
            raise _asset_error(
                "canvas_asset_dimensions_invalid",
                "export dimensions do not match its content",
            )
    metadata_json = _serialize_metadata(metadata)
    _ensure_ledger_hooks(db)
    try:
        _ensure_database_root_transaction(db)
    except Exception as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset transaction could not be started",
        ) from exc
    _require_project(db, project_id)
    _require_parent_asset(
        db,
        project_id=project_id,
        source_asset_id=source_asset_id,
    )
    try:
        savepoint = db.begin_nested()
    except Exception as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset savepoint could not be started",
        ) from exc

    asset_id = str(uuid4())
    owned_files: list[_OwnedFile] = []
    _ALLOCATION_LOCK.acquire()
    try:
        root = storage.ensure_project_tree(project_id)
        reserved_project, reserved_total = _generation_reservations(
            db,
            project_id=project_id,
        )
        storage.assert_canvas_capacity(
            project_id=project_id,
            additional_bytes=len(data),
            reserved_project_bytes=reserved_project,
            reserved_total_bytes=reserved_total,
        )
        directory = storage.ASSET_TYPE_DIRECTORIES["export"]
        destination = root / directory / f"{asset_id}{extension}"
        owned_file = _atomic_write(
            root=root,
            destination=destination,
            data=data,
            ownership=owned_files,
        )
        _register_owned_file(db, owned_file)
        asset = CanvasAsset(
            id=asset_id,
            project_id=project_id,
            asset_type="export",
            relative_path=f"{directory}/{asset_id}{extension}",
            original_filename=filename,
            mime_type=mime_type,
            byte_count=len(data),
            width=width,
            height=height,
            sha256=hashlib.sha256(data).hexdigest(),
            source_asset_id=source_asset_id,
            transparency_status="unknown",
            processor_version=processor_version,
            metadata_json=metadata_json,
        )
        db.add(asset)
        db.flush([asset])
        _commit_persistence_savepoint(savepoint)
        return asset
    except _SavepointCommittedListenerError as exc:
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset savepoint completion listener failed",
        ) from exc
    except CanvasAssetPersistenceError:
        _rollback_failed_persistence(db, savepoint, owned_files)
        raise
    except storage.CanvasStorageError as exc:
        _rollback_failed_persistence(db, savepoint, owned_files)
        raise _wrap_error(exc) from exc
    except Exception as exc:
        _rollback_failed_persistence(db, savepoint, owned_files)
        raise _asset_error(
            "canvas_asset_database_failed",
            "canvas asset database flush failed",
        ) from exc
    finally:
        _ALLOCATION_LOCK.release()
