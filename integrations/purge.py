"""FK-safe connection purge after contained archive/export file deletion."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from integration_models import (
    IntegrationArchiveManifest,
    IntegrationAuthorization,
    IntegrationConnection,
    IntegrationExportJob,
    IntegrationJob,
)
from integrations.exports import resolve_export_path
from integrations.types import ExportStatus, JobType


_ARCHIVE_SUFFIX = ".jsonl.gz.aes"


class PurgeFileError(OSError):
    """Retryable purge file failure without path or OS error disclosure."""


@dataclass(frozen=True, slots=True)
class PurgeResult:
    connection_deleted: bool
    authorization_deleted: bool
    archive_files_deleted: int
    export_files_deleted: int


def resolve_purge_archive_path(
    *,
    archive_dir: os.PathLike[str] | str,
    relative_path: str,
) -> Path:
    try:
        root = Path(os.fspath(archive_dir)).resolve(strict=False)
    except (TypeError, ValueError, OSError):
        raise PurgeFileError("Unable to resolve purge archive") from None
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or relative_path != relative_path.strip()
        or "\\" in relative_path
        or ":" in relative_path
        or "\x00" in relative_path
        or not relative_path.endswith(_ARCHIVE_SUFFIX)
    ):
        raise PurgeFileError("Unable to resolve purge archive")
    logical = PurePosixPath(relative_path)
    if (
        logical.is_absolute()
        or any(part in {"", ".", ".."} for part in logical.parts)
        or logical.as_posix() != relative_path
    ):
        raise PurgeFileError("Unable to resolve purge archive")
    candidate = root.joinpath(*logical.parts).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise PurgeFileError("Unable to resolve purge archive")
    return candidate


def _delete_path(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        raise PurgeFileError("Unable to delete purge file") from None
    return True


def _export_contains_connection(export_job, connection: IntegrationConnection) -> bool:
    filters = export_job.filters if isinstance(export_job.filters, dict) else {}
    if filters.get("connection_id") == connection.id:
        return True
    included = filters.get("_included_connection_ids")
    if isinstance(included, list) and connection.id in included:
        return True
    if "_included_connection_ids" in filters:
        return False
    provider = filters.get("provider")
    could_include_provider = provider in {None, connection.provider.value}
    return could_include_provider and (
        export_job.status in {ExportStatus.QUEUED, ExportStatus.RUNNING}
        or bool(export_job.relative_file_path)
    )


def purge_connection_data(
    db: Session,
    *,
    connection_id: int,
    archive_dir: os.PathLike[str] | str,
    current_job_id: int | None = None,
) -> PurgeResult:
    """Delete files first, then cascade only one connection in caller transaction."""

    if type(connection_id) is not int or connection_id <= 0:
        raise ValueError("connection_id must be a positive integer")
    if current_job_id is not None and (type(current_job_id) is not int or current_job_id <= 0):
        raise ValueError("current_job_id must be a positive integer")
    preview = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id
        )
    )
    if preview is None:
        return PurgeResult(False, False, 0, 0)
    authorization = db.scalar(
        select(IntegrationAuthorization)
        .where(IntegrationAuthorization.id == preview.authorization_id)
        .with_for_update()
    )
    connection = db.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.id == connection_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if connection is None:
        return PurgeResult(False, False, 0, 0)

    manifests = db.scalars(
        select(IntegrationArchiveManifest).where(
            IntegrationArchiveManifest.connection_id == connection_id
        )
    ).all()
    export_jobs = [
        export_job
        for export_job in db.scalars(
            select(IntegrationExportJob)
            .order_by(IntegrationExportJob.id)
            .with_for_update()
        ).all()
        if _export_contains_connection(export_job, connection)
    ]
    archive_deleted = 0
    export_deleted = 0
    for manifest in manifests:
        path = resolve_purge_archive_path(
            archive_dir=archive_dir,
            relative_path=manifest.relative_path,
        )
        archive_deleted += int(_delete_path(path))
    for export_job in export_jobs:
        if not export_job.relative_file_path:
            continue
        try:
            path = resolve_export_path(
                archive_dir=archive_dir,
                relative_path=export_job.relative_file_path,
            )
        except ValueError:
            raise PurgeFileError("Unable to resolve purge export") from None
        export_deleted += int(_delete_path(path))

    job_delete = delete(IntegrationJob).where(
        IntegrationJob.payload["connection_id"].as_integer() == connection_id
    )
    if current_job_id is not None:
        job_delete = job_delete.where(IntegrationJob.id != current_job_id)
    db.execute(job_delete)
    export_job_ids = [export_job.id for export_job in export_jobs]
    if export_job_ids:
        db.execute(
            delete(IntegrationJob).where(
                IntegrationJob.job_type == JobType.EXPORT,
                IntegrationJob.payload["export_job_id"]
                .as_integer()
                .in_(export_job_ids),
            )
        )
    for export_job in export_jobs:
        db.delete(export_job)

    authorization_id = connection.authorization_id
    db.delete(connection)
    db.flush()
    remaining = int(
        db.scalar(
            select(func.count()).select_from(IntegrationConnection).where(
                IntegrationConnection.authorization_id == authorization_id
            )
        )
        or 0
    )
    authorization_deleted = False
    if remaining == 0 and authorization is not None:
        db.delete(authorization)
        authorization_deleted = True
    return PurgeResult(
        connection_deleted=True,
        authorization_deleted=authorization_deleted,
        archive_files_deleted=archive_deleted,
        export_files_deleted=export_deleted,
    )


__all__ = [
    "PurgeFileError",
    "PurgeResult",
    "purge_connection_data",
    "resolve_purge_archive_path",
]
