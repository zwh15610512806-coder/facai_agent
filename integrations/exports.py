"""Formula-safe atomic CSV/XLSX generation for audited integration exports."""

from __future__ import annotations

import csv
import os
import re
import tempfile
from collections.abc import Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from integration_models import IntegrationConnection, IntegrationExportJob
from integrations.redaction import assert_payload_safe
from integrations.schemas import ExportCreateRequest
from integrations.sync.queue import enqueue_job
from integrations.reporting import (
    ReportingRange,
    SHANGHAI,
    list_ad_entities,
    list_ad_metrics,
    list_orders,
    list_products,
    list_refunds,
)
from integrations.types import (
    AdEntityType,
    ConnectionStatus,
    ExportStatus,
    JobType,
    MetricGranularity,
    OrderStatus,
    ProductStatus,
    Provider,
    RefundStatus,
    ResourceType,
)


_COLUMN_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_EXPORT_TEMP_NAME = re.compile(
    r"^\.(?P<public_id>[0-9a-f-]{36})\.[A-Za-z0-9_-]{1,32}\."
    r"(?P<format>csv|xlsx)\.tmp$"
)
_COLUMN_KINDS = frozenset({"text", "decimal", "integer", "datetime"})
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_EXPORT_LIFETIME = timedelta(hours=24)
_EXPORT_ORPHAN_MINIMUM_AGE = timedelta(hours=1)

_EXPORT_COLUMNS: dict[ResourceType, tuple[ExportColumn, ...]] = {}


class ExportWriteError(OSError):
    """Stable export failure that never exposes filesystem or row contents."""


class ExportRequestConflict(ValueError):
    """The requested connection cannot participate in a new export."""


@dataclass(frozen=True, slots=True)
class ExportColumn:
    key: str
    heading: str
    kind: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or _COLUMN_KEY.fullmatch(self.key) is None:
            raise ValueError("export column key is invalid")
        if (
            not isinstance(self.heading, str)
            or not self.heading
            or self.heading != self.heading.strip()
            or len(self.heading) > 100
            or any(ord(character) < 32 or ord(character) == 127 for character in self.heading)
        ):
            raise ValueError("export column heading is invalid")
        if self.kind not in _COLUMN_KINDS:
            raise ValueError("export column kind is invalid")


_EXPORT_COLUMNS.update(
    {
        ResourceType.ORDERS: (
            ExportColumn("external_order_id", "平台订单号", "text"),
            ExportColumn("provider", "平台", "text"),
            ExportColumn("connection_id", "连接 ID", "integer"),
            ExportColumn("status", "状态", "text"),
            ExportColumn("raw_status", "平台状态", "text"),
            ExportColumn("currency", "币种", "text"),
            ExportColumn("order_amount", "订单金额", "decimal"),
            ExportColumn("paid_amount", "实付金额", "decimal"),
            ExportColumn("discount_amount", "优惠金额", "decimal"),
            ExportColumn("shipping_amount", "运费", "decimal"),
            ExportColumn("ordered_at", "下单时间", "text"),
            ExportColumn("paid_at", "支付时间", "text"),
        ),
        ResourceType.PRODUCTS: (
            ExportColumn("external_product_id", "平台商品 ID", "text"),
            ExportColumn("provider", "平台", "text"),
            ExportColumn("connection_id", "连接 ID", "integer"),
            ExportColumn("title", "商品标题", "text"),
            ExportColumn("status", "状态", "text"),
            ExportColumn("raw_status", "平台状态", "text"),
            ExportColumn("category", "类目", "text"),
            ExportColumn("price", "价格", "decimal"),
            ExportColumn("currency", "币种", "text"),
            ExportColumn("link_status", "产品关联状态", "text"),
        ),
        ResourceType.REFUNDS: (
            ExportColumn("external_refund_id", "平台退款 ID", "text"),
            ExportColumn("external_order_id", "平台订单号", "text"),
            ExportColumn("provider", "平台", "text"),
            ExportColumn("connection_id", "连接 ID", "integer"),
            ExportColumn("status", "状态", "text"),
            ExportColumn("raw_status", "平台状态", "text"),
            ExportColumn("amount", "退款金额", "decimal"),
            ExportColumn("currency", "币种", "text"),
            ExportColumn("reason_code", "原因码", "text"),
            ExportColumn("completed_at", "完成时间", "text"),
        ),
        ResourceType.AD_ENTITIES: (
            ExportColumn("external_entity_id", "广告实体 ID", "text"),
            ExportColumn("entity_type", "实体层级", "text"),
            ExportColumn("provider", "平台", "text"),
            ExportColumn("connection_id", "连接 ID", "integer"),
            ExportColumn("name", "名称", "text"),
            ExportColumn("status", "状态", "text"),
            ExportColumn("raw_status", "平台状态", "text"),
            ExportColumn("platform_updated_at", "平台更新时间", "text"),
        ),
        ResourceType.AD_DAILY_METRICS: (
            ExportColumn("external_entity_id", "广告实体 ID", "text"),
            ExportColumn("entity_type", "实体层级", "text"),
            ExportColumn("provider", "平台", "text"),
            ExportColumn("connection_id", "连接 ID", "integer"),
            ExportColumn("stat_date", "日期", "text"),
            ExportColumn("spend", "广告消耗", "decimal"),
            ExportColumn("impressions", "曝光", "integer"),
            ExportColumn("clicks", "点击", "integer"),
            ExportColumn("orders", "归因订单", "integer"),
            ExportColumn("attributed_sales", "广告归因成交", "decimal"),
            ExportColumn("currency", "币种", "text"),
        ),
    }
)


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    relative_path: str
    row_count: int


@dataclass(slots=True)
class ExportPublicationTracker:
    """Identify only an artifact published by the current generation call."""

    relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class ExportOrphanScanResult:
    deleted_paths: tuple[str, ...]
    failure_count: int


def escape_spreadsheet_text(value: str) -> str:
    """Neutralize formula prefixes identically for CSV and Excel."""

    if not isinstance(value, str):
        raise TypeError("spreadsheet text must be a string")
    dangerous_leading_control = value.startswith(("\t", "\r", "\n"))
    trimmed = value.lstrip()
    if dangerous_leading_control or trimmed.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _canonical_public_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("export public id must be a UUID")
    try:
        selected = str(UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("export public id must be a UUID") from None
    if value != selected:
        raise ValueError("export public id must be a canonical UUID")
    return selected


def _selected_columns(columns: tuple[ExportColumn, ...]) -> tuple[ExportColumn, ...]:
    if not isinstance(columns, tuple) or not columns:
        raise ValueError("columns must be a non-empty tuple")
    if any(not isinstance(column, ExportColumn) for column in columns):
        raise ValueError("columns must contain ExportColumn values")
    keys = [column.key for column in columns]
    if len(keys) != len(set(keys)):
        raise ValueError("export column keys must be unique")
    return columns


def _utc_iso(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("export datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _cell_value(value: object, *, kind: str, xlsx: bool) -> object:
    if value is None:
        return ""
    if kind == "text":
        if not isinstance(value, str):
            raise TypeError("export text value must be a string")
        return escape_spreadsheet_text(value)
    if kind == "decimal":
        if not isinstance(value, Decimal) or not value.is_finite():
            raise TypeError("export decimal value must be a finite Decimal")
        return value if xlsx else format(value, "f")
    if kind == "integer":
        if type(value) is not int:
            raise TypeError("export integer value must be an integer")
        return value
    if kind == "datetime":
        return _utc_iso(value)
    raise ValueError("export column kind is invalid")  # pragma: no cover


def _text_cell(sheet, value: str) -> WriteOnlyCell:
    cell = WriteOnlyCell(sheet, value=value)
    cell.data_type = "s"
    return cell


def _write_csv(
    temp_path: Path,
    *,
    columns: tuple[ExportColumn, ...],
    rows: Iterable[Mapping[str, object]],
) -> int:
    count = 0
    with temp_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow([column.heading for column in columns])
        for row in rows:
            if not isinstance(row, Mapping):
                raise TypeError("export rows must be mappings")
            writer.writerow(
                [
                    _cell_value(row.get(column.key), kind=column.kind, xlsx=False)
                    for column in columns
                ]
            )
            count += 1
        stream.flush()
        os.fsync(stream.fileno())
    return count


def _write_xlsx(
    temp_path: Path,
    *,
    columns: tuple[ExportColumn, ...],
    rows: Iterable[Mapping[str, object]],
) -> int:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("数据")
    sheet.append([_text_cell(sheet, column.heading) for column in columns])
    count = 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("export rows must be mappings")
        cells: list[object] = []
        for column in columns:
            value = _cell_value(row.get(column.key), kind=column.kind, xlsx=True)
            if column.kind in {"text", "datetime"} or value == "":
                cells.append(_text_cell(sheet, str(value)))
            else:
                cells.append(value)
        sheet.append(cells)
        count += 1
    workbook.save(temp_path)
    with temp_path.open("r+b") as stream:
        os.fsync(stream.fileno())
    return count


def write_export_file(
    *,
    archive_dir: os.PathLike[str] | str,
    public_id: str,
    export_format: str,
    columns: tuple[ExportColumn, ...],
    rows: Iterable[Mapping[str, object]],
) -> ExportArtifact:
    """Write one explicit-column export and atomically publish the final file."""

    selected_id = _canonical_public_id(public_id)
    if export_format not in {"csv", "xlsx"}:
        raise ValueError("export format must be csv or xlsx")
    selected_columns = _selected_columns(columns)
    if isinstance(rows, (str, bytes, bytearray, Mapping)):
        raise TypeError("rows must be an iterable of mappings")
    try:
        root = Path(os.fspath(archive_dir)).resolve(strict=False)
        export_dir = (root / "exports").resolve(strict=False)
    except (TypeError, ValueError, OSError):
        raise ExportWriteError("Unable to write integration export") from None
    if not export_dir.is_relative_to(root):  # pragma: no cover - constant child
        raise ExportWriteError("Unable to write integration export")
    relative_path = f"exports/{selected_id}.{export_format}"
    final_path = export_dir / f"{selected_id}.{export_format}"
    temp_path: Path | None = None
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        file_descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{selected_id}.",
            suffix=f".{export_format}.tmp",
            dir=export_dir,
        )
        os.close(file_descriptor)
        temp_path = Path(temp_name)
        if export_format == "csv":
            row_count = _write_csv(
                temp_path,
                columns=selected_columns,
                rows=rows,
            )
        else:
            row_count = _write_xlsx(
                temp_path,
                columns=selected_columns,
                rows=rows,
            )
        os.replace(temp_path, final_path)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ExportWriteError("Unable to write integration export") from None
    return ExportArtifact(relative_path=relative_path, row_count=row_count)


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def create_export_job(
    db: Session,
    *,
    requester_session_digest: str,
    request: ExportCreateRequest,
    now: datetime,
) -> IntegrationExportJob:
    """Stage export metadata and one idempotent worker job in the caller transaction."""

    if (
        not isinstance(requester_session_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", requester_session_digest) is None
    ):
        raise ValueError("requester session digest is invalid")
    if not isinstance(request, ExportCreateRequest):
        raise TypeError("request must be an ExportCreateRequest")
    selected_now = _aware_utc(now, field_name="now")
    filters = request.filters.model_dump(mode="json", exclude_none=True)
    assert_payload_safe(filters)
    connection_id = filters.get("connection_id")
    if connection_id is not None:
        connection = db.scalar(
            select(IntegrationConnection)
            .where(IntegrationConnection.id == connection_id)
            .with_for_update(read=True)
        )
        if connection is None or connection.status is ConnectionStatus.DISABLED:
            raise ExportRequestConflict("connection is unavailable for export")
    export_job = IntegrationExportJob(
        requester_session_digest=requester_session_digest,
        resource_type=request.resource_type,
        filters=filters,
        format=request.format,
        status=ExportStatus.QUEUED,
        row_count=0,
        created_at=selected_now,
        expires_at=selected_now + _EXPORT_LIFETIME,
    )
    db.add(export_job)
    db.flush((export_job,))
    enqueue_job(
        db,
        job_type=JobType.EXPORT,
        target_id=export_job.id,
        logical_request={"export_job_id": export_job.id},
        payload={"export_job_id": export_job.id},
        priority=20,
    )
    return export_job


def export_job_view(export_job: IntegrationExportJob, *, now: datetime) -> dict[str, object]:
    selected_now = _aware_utc(now, field_name="now")
    status = export_job.status
    if status is ExportStatus.READY and export_job.expires_at <= selected_now:
        status = ExportStatus.EXPIRED
    ready = status is ExportStatus.READY
    return {
        "id": export_job.public_id,
        "resource_type": export_job.resource_type.value,
        "format": export_job.format,
        "status": status.value,
        "row_count": export_job.row_count,
        "created_at": _aware_utc(export_job.created_at, field_name="created_at")
        .isoformat()
        .replace("+00:00", "Z"),
        "expires_at": _aware_utc(export_job.expires_at, field_name="expires_at")
        .isoformat()
        .replace("+00:00", "Z"),
        "error_code": export_job.error_code,
        "error_summary": export_job.error_summary,
        "download_url": (
            f"/api/integrations/exports/{export_job.public_id}/download"
            if ready
            else None
        ),
    }


def get_export_job(db: Session, public_id: str) -> IntegrationExportJob | None:
    selected_id = _canonical_public_id(public_id)
    return db.scalar(
        select(IntegrationExportJob).where(IntegrationExportJob.public_id == selected_id)
    )


def resolve_export_path(
    *,
    archive_dir: os.PathLike[str] | str,
    relative_path: str,
) -> Path:
    if not isinstance(relative_path, str):
        raise ValueError("export relative path is invalid")
    matched = re.fullmatch(
        r"exports/(?P<public_id>[0-9a-f-]{36})\.(?P<format>csv|xlsx)",
        relative_path,
    )
    if matched is None:
        raise ValueError("export relative path is invalid")
    public_id = _canonical_public_id(matched.group("public_id"))
    if relative_path != f"exports/{public_id}.{matched.group('format')}":
        raise ValueError("export relative path is invalid")
    root = Path(os.fspath(archive_dir)).resolve(strict=False)
    candidate = root.joinpath(*relative_path.split("/")).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise ValueError("export relative path escapes archive_dir")
    return candidate


def scan_orphan_exports(
    *,
    archive_dir: os.PathLike[str] | str,
    known_relative_paths: Collection[str],
    now: datetime,
) -> ExportOrphanScanResult:
    """Delete canonical export artifacts older than one hour with no DB row."""

    selected_now = _aware_utc(now, field_name="now")
    if isinstance(known_relative_paths, (str, bytes, bytearray)):
        raise TypeError("known_relative_paths must be a collection")
    known: set[str] = set()
    for relative_path in known_relative_paths:
        resolve_export_path(
            archive_dir=archive_dir,
            relative_path=relative_path,
        )
        known.add(relative_path)
    root = Path(os.fspath(archive_dir)).resolve(strict=False)
    export_dir = (root / "exports").resolve(strict=False)
    if not export_dir.is_relative_to(root) or not export_dir.exists():
        return ExportOrphanScanResult((), 0)
    cutoff = (selected_now - _EXPORT_ORPHAN_MINIMUM_AGE).timestamp()
    deleted: list[str] = []
    failures = 0
    for candidate in sorted((*export_dir.glob("*.csv"), *export_dir.glob("*.xlsx"))):
        relative_path = f"exports/{candidate.name}"
        try:
            resolved = resolve_export_path(
                archive_dir=root,
                relative_path=relative_path,
            )
            if resolved != candidate.resolve(strict=False):
                failures += 1
                continue
            if relative_path in known or candidate.stat().st_mtime >= cutoff:
                continue
            candidate.unlink()
            deleted.append(relative_path)
        except (FileNotFoundError,):
            continue
        except (OSError, ValueError):
            failures += 1
    for candidate in sorted(export_dir.glob(".*.tmp")):
        matched = _EXPORT_TEMP_NAME.fullmatch(candidate.name)
        if matched is None:
            continue
        try:
            _canonical_public_id(matched.group("public_id"))
            resolved = candidate.resolve(strict=False)
            if not resolved.is_relative_to(export_dir):
                failures += 1
                continue
            if candidate.stat().st_mtime >= cutoff:
                continue
            candidate.unlink()
            deleted.append(f"exports/{candidate.name}")
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            failures += 1
    return ExportOrphanScanResult(tuple(deleted), failures)


def _export_reporting_range(filters: Mapping[str, object], *, today: date) -> ReportingRange:
    raw_from = filters.get("date_from")
    raw_to = filters.get("date_to")
    selected_to = date.fromisoformat(raw_to) if isinstance(raw_to, str) else today
    selected_from = (
        date.fromisoformat(raw_from)
        if isinstance(raw_from, str)
        else selected_to - timedelta(days=29)
    )
    if selected_from > selected_to:
        raise ValueError("export date range is invalid")
    if (selected_to - selected_from).days + 1 > 366:
        raise ValueError("export date range must not exceed 366 days")
    start_local = datetime.combine(selected_from, time.min, tzinfo=SHANGHAI)
    end_local = datetime.combine(
        selected_to + timedelta(days=1),
        time.min,
        tzinfo=SHANGHAI,
    )
    return ReportingRange(
        date_from=selected_from,
        date_to=selected_to,
        start_at=start_local.astimezone(timezone.utc),
        end_at=end_local.astimezone(timezone.utc),
        days=(selected_to - selected_from).days + 1,
    )


def _enum_filter(enum_type: type, value: object):
    if value is None:
        return None
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise ValueError("export status filter is invalid") from None


def _iter_export_items(
    db: Session,
    *,
    export_job: IntegrationExportJob,
    now: datetime,
    allowed_connection_ids: Collection[int] | None = None,
) -> Iterator[dict[str, object]]:
    filters = export_job.filters if isinstance(export_job.filters, dict) else {}
    selected_range = _export_reporting_range(
        filters,
        today=now.astimezone(SHANGHAI).date(),
    )
    provider = _enum_filter(Provider, filters.get("provider"))
    connection_id = filters.get("connection_id")
    if connection_id is not None and (type(connection_id) is not int or connection_id <= 0):
        raise ValueError("export connection filter is invalid")
    search = filters.get("search")
    page = 1
    columns = _EXPORT_COLUMNS[export_job.resource_type]
    while True:
        common = {
            "db": db,
            "reporting_range": selected_range,
            "provider": provider,
            "connection_id": connection_id,
            "page": page,
            "per_page": 200,
            "allowed_connection_ids": allowed_connection_ids,
        }
        if export_job.resource_type is ResourceType.ORDERS:
            result = list_orders(
                **common,
                status=_enum_filter(OrderStatus, filters.get("status")),
                search=search,
            )
        elif export_job.resource_type is ResourceType.PRODUCTS:
            result = list_products(
                **common,
                status=_enum_filter(ProductStatus, filters.get("status")),
                search=search,
                link_status=filters.get("link_status"),
            )
        elif export_job.resource_type is ResourceType.REFUNDS:
            result = list_refunds(
                **common,
                status=_enum_filter(RefundStatus, filters.get("status")),
                search=search,
            )
        elif export_job.resource_type is ResourceType.AD_ENTITIES:
            result = list_ad_entities(
                **common,
                entity_type=_enum_filter(AdEntityType, filters.get("entity_type")),
                search=search,
            )
        elif export_job.resource_type is ResourceType.AD_DAILY_METRICS:
            result = list_ad_metrics(
                **common,
                entity_type=_enum_filter(AdEntityType, filters.get("entity_type")),
                granularity=_enum_filter(
                    MetricGranularity,
                    filters.get("granularity"),
                ),
            )
        else:  # guarded by ExportCreateRequest and DB enum
            raise ValueError("export resource is unavailable")
        for item in result.items:
            row = dict(item)
            for column in columns:
                if column.kind != "decimal":
                    continue
                value = row.get(column.key)
                if isinstance(value, str):
                    row[column.key] = Decimal(value)
            yield row
        if page >= result.total_pages:
            break
        page += 1


def generate_export_job(
    db: Session,
    *,
    export_job_id: int,
    archive_dir: os.PathLike[str] | str,
    now: datetime,
    terminal_failure: bool = True,
    publication: ExportPublicationTracker | None = None,
) -> IntegrationExportJob:
    """Generate one queued export; caller commits model state after the atomic file."""

    selected_now = _aware_utc(now, field_name="now")
    if type(terminal_failure) is not bool:
        raise ValueError("terminal_failure must be a boolean")
    if publication is not None and not isinstance(
        publication,
        ExportPublicationTracker,
    ):
        raise TypeError("publication must be an ExportPublicationTracker")
    if publication is not None:
        publication.relative_path = None
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
    preview = db.scalar(
        select(IntegrationExportJob).where(IntegrationExportJob.id == export_job_id)
    )
    if preview is None:
        raise LookupError("export job not found")
    preview_filters = preview.filters if isinstance(preview.filters, dict) else {}
    connection_conditions = [
        IntegrationConnection.status != ConnectionStatus.DISABLED,
    ]
    requested_connection_id = preview_filters.get("connection_id")
    if requested_connection_id is not None:
        connection_conditions.append(
            IntegrationConnection.id == requested_connection_id
        )
    requested_provider = preview_filters.get("provider")
    if requested_provider is not None:
        connection_conditions.append(
            IntegrationConnection.provider == Provider(requested_provider)
        )
    allowed_connection_ids = tuple(
        db.scalars(
            select(IntegrationConnection.id)
            .where(*connection_conditions)
            .order_by(IntegrationConnection.id)
            .with_for_update(read=True)
        ).all()
    )
    export_job = db.scalar(
        select(IntegrationExportJob)
        .where(IntegrationExportJob.id == export_job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if export_job is None:  # deleted after the preview in a concurrent purge
        raise LookupError("export job not found")
    if export_job.status is ExportStatus.READY:
        return export_job
    if export_job.expires_at <= selected_now:
        export_job.status = ExportStatus.EXPIRED
        return export_job
    export_job.status = ExportStatus.RUNNING
    export_job.started_at = export_job.started_at or selected_now
    export_job.error_code = None
    export_job.error_summary = None
    db.flush((export_job,))
    try:
        included_connection_ids: set[int] = set()

        def tracked_rows() -> Iterator[dict[str, object]]:
            for row in _iter_export_items(
                db,
                export_job=export_job,
                now=selected_now,
                allowed_connection_ids=allowed_connection_ids,
            ):
                connection_id = row.get("connection_id")
                if type(connection_id) is int and connection_id > 0:
                    included_connection_ids.add(connection_id)
                yield row

        artifact = write_export_file(
            archive_dir=archive_dir,
            public_id=export_job.public_id,
            export_format=export_job.format,
            columns=_EXPORT_COLUMNS[export_job.resource_type],
            rows=tracked_rows(),
        )
        if publication is not None:
            publication.relative_path = artifact.relative_path
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        export_job.status = (
            ExportStatus.FAILED if terminal_failure else ExportStatus.RUNNING
        )
        export_job.error_code = (
            "export_generation_failed" if terminal_failure else None
        )
        export_job.error_summary = (
            "integration export generation failed" if terminal_failure else None
        )
        export_job.completed_at = selected_now if terminal_failure else None
        export_job.relative_file_path = None
        export_job.row_count = 0
        return export_job
    filters = dict(export_job.filters) if isinstance(export_job.filters, dict) else {}
    filters["_included_connection_ids"] = sorted(included_connection_ids)
    assert_payload_safe(filters)
    export_job.filters = filters
    export_job.status = ExportStatus.READY
    export_job.relative_file_path = artifact.relative_path
    export_job.row_count = artifact.row_count
    export_job.completed_at = selected_now
    return export_job


def expire_export_files(
    db: Session,
    *,
    archive_dir: os.PathLike[str] | str,
    now: datetime,
) -> tuple[int, int]:
    """Delete expired files before marking jobs expired; return deleted/retry counts."""

    selected_now = _aware_utc(now, field_name="now")
    jobs = db.scalars(
        select(IntegrationExportJob).where(
            IntegrationExportJob.expires_at <= selected_now,
            IntegrationExportJob.status != ExportStatus.EXPIRED,
        ).with_for_update(skip_locked=True)
    ).all()
    deleted = 0
    retry = 0
    for job in jobs:
        if job.relative_file_path:
            try:
                resolve_export_path(
                    archive_dir=archive_dir,
                    relative_path=job.relative_file_path,
                ).unlink(missing_ok=True)
            except (OSError, ValueError):
                retry += 1
                continue
        job.status = ExportStatus.EXPIRED
        deleted += 1
    return deleted, retry


__all__ = [
    "ExportArtifact",
    "ExportColumn",
    "ExportOrphanScanResult",
    "ExportPublicationTracker",
    "ExportWriteError",
    "escape_spreadsheet_text",
    "create_export_job",
    "export_job_view",
    "get_export_job",
    "generate_export_job",
    "expire_export_files",
    "resolve_export_path",
    "scan_orphan_exports",
    "write_export_file",
]
