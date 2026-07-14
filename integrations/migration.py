"""Verified, fail-closed SQLite-to-PostgreSQL data migration support."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import Any, Callable, Mapping
from urllib.parse import quote

from alembic.script import ScriptDirectory
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    JSON,
    UniqueConstraint,
    and_,
    create_engine,
    exists,
    func,
    inspect,
    null,
    select,
    text,
)
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.exc import SQLAlchemyError

# Model imports are deliberately explicit so CLI use sees the complete metadata.
import commerce_models  # noqa: F401
import creator_models  # noqa: F401
import integration_models  # noqa: F401
import models  # noqa: F401
from database import Base, alembic_config


class MigrationError(RuntimeError):
    """A safe, operator-facing migration rejection."""


@dataclass(frozen=True, slots=True)
class BackupReport:
    source_path: Path
    source_size: int
    source_sha256: str
    source_database_sha256: str
    source_wal_path: Path | None
    source_wal_size: int
    source_wal_sha256: str | None
    source_integrity_check: str
    source_page_count: int
    backup_path: Path
    backup_size: int
    backup_sha256: str
    backup_integrity_check: str
    backup_page_count: int
    ok: bool


@dataclass(frozen=True, slots=True)
class SnapshotEvidence:
    """Immutable source and verified-snapshot evidence for one migration run."""

    source_path: Path
    source_size: int
    source_sha256: str
    source_database_sha256: str
    source_wal_path: Path | None
    source_wal_size: int
    source_wal_sha256: str | None
    source_integrity_check: str
    source_page_count: int
    snapshot_path: Path | None
    snapshot_size: int
    snapshot_sha256: str
    snapshot_integrity_check: str
    snapshot_page_count: int
    retained: bool
    ok: bool

    def __post_init__(self) -> None:
        if self.retained and self.snapshot_path is None:
            raise ValueError("retained snapshot evidence requires a snapshot path")
        if not self.retained and self.snapshot_path is not None:
            raise ValueError("ephemeral snapshot evidence cannot expose a reusable path")
        if self.source_wal_path is None:
            if self.source_wal_size != 0 or self.source_wal_sha256 is not None:
                raise ValueError("absent WAL evidence must use zero size and no hash")
        elif self.source_wal_sha256 is None:
            raise ValueError("present WAL evidence requires a hash")


@dataclass(frozen=True, slots=True)
class _SQLiteState:
    database_size: int
    database_sha256: str
    wal_path: Path | None
    wal_size: int
    wal_sha256: str | None
    sha256: str


@dataclass(frozen=True, slots=True)
class LegacyColumnAdapter:
    """Documented deterministic derivation for one historical missing column."""

    description: str
    source_schema_sha256: str
    derive: Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class LegacyIgnoredColumn:
    """Documented reconciliation rule for one obsolete source-only column."""

    reason: str
    reconciliation: str


@dataclass(frozen=True, slots=True)
class TableMigrationReport:
    table: str
    source_rows: int
    target_rows: int
    orphan_foreign_keys: tuple[str, ...]
    duplicate_unique_keys: tuple[str, ...]
    json_errors: tuple[str, ...]
    synthesized_columns: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "synthesized_columns",
            MappingProxyType(dict(self.synthesized_columns)),
        )


@dataclass(frozen=True, slots=True)
class MigrationReport:
    source_path: Path
    source_sha256: str
    backup_path: Path | None
    backup_sha256: str | None
    applied: bool
    tables: tuple[TableMigrationReport, ...]
    amount_totals: Mapping[str, str]
    ok: bool
    snapshot: SnapshotEvidence
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source_path != self.snapshot.source_path:
            raise ValueError("migration source path must match snapshot evidence")
        if self.source_sha256 != self.snapshot.source_sha256:
            raise ValueError("migration source hash must match snapshot evidence")
        expected_path = (
            self.snapshot.snapshot_path if self.snapshot.retained else None
        )
        expected_sha256 = (
            self.snapshot.snapshot_sha256 if self.snapshot.retained else None
        )
        if self.backup_path != expected_path or self.backup_sha256 != expected_sha256:
            raise ValueError("migration backup aliases must match snapshot evidence")
        object.__setattr__(
            self,
            "amount_totals",
            MappingProxyType(dict(self.amount_totals)),
        )


OPTIONAL_INTEGRATION_TABLES = frozenset(
    {
        "commerce_ad_accounts",
        "commerce_ad_balance_snapshots",
        "commerce_ad_daily_metrics",
        "commerce_ad_entities",
        "commerce_ad_finance_transactions",
        "commerce_daily_metrics",
        "commerce_event_inbox",
        "commerce_inventory_snapshots",
        "commerce_order_items",
        "commerce_orders",
        "commerce_product_links",
        "commerce_products",
        "commerce_refunds",
        "commerce_settlements",
        "commerce_shipments",
        "commerce_shops",
        "commerce_skus",
        "integration_app_configs",
        "integration_archive_manifests",
        "integration_authorizations",
        "integration_connections",
        "integration_export_jobs",
        "integration_jobs",
        "integration_login_throttles",
        "integration_oauth_states",
        "integration_security_audit",
        "integration_sync_checkpoints",
        "integration_sync_errors",
        "integration_sync_runs",
        "integration_worker_heartbeats",
    }
)

AMOUNT_COLUMNS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "qianchuan_material_performance": (
            "transaction_amount",
            "user_pay_amount",
            "spend",
        ),
        "creator_collaborations": ("actual_paid_cents",),
    }
)

BATCH_SIZE = 500

SEQUENCE_SIDE_EFFECT_WARNING = (
    "PostgreSQL sequence changes are nontransactional; after any sequence-stage "
    "failure, reprovision or clean the target before retrying."
)


def _constant(value: Any) -> Callable[[Mapping[str, Any]], Any]:
    return lambda _row: value


# Keep this registry deliberately small: every entry requires its own pinned
# historical-schema fingerprint and migration test before admission.
LEGACY_COLUMN_ADAPTERS: dict[tuple[str, str], LegacyColumnAdapter] = {
    ("viral_scripts", "is_high_conversion"): LegacyColumnAdapter(
        "fingerprint 4ece88ef: historical viral scripts default to false",
        "4ece88ef1e2ecae46534018097bcd4ffe3397f3a55dd4dc3827d2d3891abeab0",
        _constant(0),
    ),
}

# No obsolete source column is currently approved for silent reconciliation.
LEGACY_IGNORED_COLUMNS: dict[tuple[str, str], LegacyIgnoredColumn] = {}


@dataclass(slots=True)
class _TableState:
    table: Any
    source_rows: int = 0
    target_rows: int = 0
    orphan_foreign_keys: list[str] | None = None
    duplicate_unique_keys: list[str] | None = None
    json_errors: list[str] | None = None
    synthesized_columns: dict[str, int] | None = None

    def __post_init__(self) -> None:
        self.orphan_foreign_keys = []
        self.duplicate_unique_keys = []
        self.json_errors = []
        self.synthesized_columns = {}

    def report(self) -> TableMigrationReport:
        return TableMigrationReport(
            table=self.table.name,
            source_rows=self.source_rows,
            target_rows=self.target_rows,
            orphan_foreign_keys=tuple(self.orphan_foreign_keys or ()),
            duplicate_unique_keys=tuple(self.duplicate_unique_keys or ()),
            json_errors=tuple(self.json_errors or ()),
            synthesized_columns=self.synthesized_columns or {},
        )

    @property
    def has_errors(self) -> bool:
        return bool(
            self.orphan_foreign_keys
            or self.duplicate_unique_keys
            or self.json_errors
        )


@dataclass(frozen=True, slots=True)
class _UniqueSpec:
    name: str
    columns: tuple[str, ...]
    where: Any | None
    nulls_not_distinct: bool


def _quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _source_table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        if not str(row[0]).startswith("sqlite_")
    }


def _source_columns(connection: sqlite3.Connection, table_name: str) -> tuple[str, ...]:
    quoted = _quote_sqlite_identifier(table_name)
    return tuple(str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted})"))


def _source_schema_fingerprint(
    connection: sqlite3.Connection,
    table_name: str,
) -> str:
    quoted = _quote_sqlite_identifier(table_name)
    rows = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
    signature = "\n".join(
        "|".join("" if value is None else str(value) for value in row)
        for row in rows
    )
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()


def _convert_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        converted = value
    elif isinstance(value, str):
        converted = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        raise ValueError("expected an ISO datetime")
    if converted.tzinfo is not None:
        converted = converted.astimezone(timezone.utc).replace(tzinfo=None)
    return converted


def _convert_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value.strip()[:10])
    raise ValueError("expected an ISO date")


def _convert_json(column: Any, value: Any) -> Any:
    processor = column.type.result_processor(sqlite_dialect(), None)
    converted = processor(value) if processor is not None else value
    if converted is None:
        return JSON.NULL
    json.dumps(converted, ensure_ascii=False, allow_nan=False)
    return converted


def _convert_source_value(column: Any, value: Any) -> Any:
    if isinstance(column.type, JSON):
        if value is None:
            if not column.nullable:
                raise ValueError("SQL NULL in a non-nullable JSON column")
            return null()
        return _convert_json(column, value)
    if value is None:
        if not column.nullable and not column.primary_key:
            raise ValueError("NULL in a non-nullable column")
        return None
    if isinstance(column.type, DateTime):
        return _convert_datetime(value)
    if isinstance(column.type, Date):
        return _convert_date(value)
    if isinstance(column.type, Boolean):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"0", "false"}:
                return False
            if normalized in {"1", "true"}:
                return True
            raise ValueError("expected a boolean")
        return bool(value)
    return value


def _unique_specs(table: Any) -> tuple[_UniqueSpec, ...]:
    specs: list[_UniqueSpec] = []
    for constraint in table.constraints:
        if not isinstance(constraint, UniqueConstraint):
            continue
        columns = tuple(column.name for column in constraint.columns)
        name = constraint.name or f"uq_{table.name}_{'_'.join(columns)}"
        nulls_not_distinct = bool(
            constraint.dialect_options["postgresql"].get("nulls_not_distinct")
        )
        specs.append(_UniqueSpec(name, columns, None, nulls_not_distinct))
    for index in table.indexes:
        if not index.unique:
            continue
        columns = tuple(column.name for column in index.columns)
        where = index.dialect_options["postgresql"].get("where")
        if where is None:
            where = index.dialect_options["sqlite"].get("where")
        nulls_not_distinct = bool(
            index.dialect_options["postgresql"].get("nulls_not_distinct")
        )
        specs.append(
            _UniqueSpec(
                index.name or f"uq_{table.name}_{'_'.join(columns)}",
                columns,
                where,
                nulls_not_distinct,
            )
        )
    return tuple(sorted(specs, key=lambda item: item.name))


_IS_NOT_NULL = re.compile(r'^"?([A-Za-z_][A-Za-z0-9_]*)"?\s+IS\s+NOT\s+NULL$', re.I)
_EQUALS_LITERAL = re.compile(
    r'^"?([A-Za-z_][A-Za-z0-9_]*)"?\s*=\s*[\'\"]([^\'\"]*)[\'\"]$',
    re.I,
)


def _matches_partial(row: Mapping[str, Any], where: Any | None) -> bool:
    if where is None:
        return True
    expression = str(where).strip()
    while expression.startswith("(") and expression.endswith(")"):
        expression = expression[1:-1].strip()
    not_null = _IS_NOT_NULL.fullmatch(expression)
    if not_null:
        return row.get(not_null.group(1)) is not None
    equals = _EQUALS_LITERAL.fullmatch(expression)
    if equals:
        return row.get(equals.group(1)) == equals.group(2)
    raise MigrationError(
        "A declared partial unique predicate cannot be validated deterministically"
    )


def _canonical_key_value(value: Any) -> list[Any]:
    if isinstance(value, Enum):
        return _canonical_key_value(value.value)
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, Decimal):
        return ["decimal", format(value, "f")]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MigrationError("Diagnostic key material is not finite")
        return ["float", value.hex()]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, datetime):
        normalized = value
        if normalized.tzinfo is not None:
            normalized = normalized.astimezone(timezone.utc)
        return ["datetime", normalized.isoformat(timespec="microseconds")]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, bytes):
        return ["bytes_sha256", hashlib.sha256(value).hexdigest()]
    raise MigrationError("Diagnostic key material has an unsupported type")


def _key_sha256(key: tuple[Any, ...]) -> str:
    canonical = json.dumps(
        [_canonical_key_value(value) for value in key],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(b"facai-diagnostic-key-v1\x00")
    digest.update(canonical)
    return digest.hexdigest()


def _key_set_sha256(keys: list[tuple[Any, ...]]) -> str:
    key_digests = sorted(_key_sha256(key) for key in keys)
    digest = hashlib.sha256()
    digest.update(b"facai-diagnostic-key-set-v1\x00")
    for item in key_digests:
        digest.update(item.encode("ascii"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _describe_key(
    name: str,
    key: tuple[Any, ...],
    *,
    duplicate_count: int,
) -> str:
    key_sha256 = _key_sha256(key)
    return (
        f"{name}: duplicate_count={duplicate_count} "
        f"key_sha256={key_sha256}"
    )


def _validate_source_uniques(
    table: Any,
    rows: list[dict[str, Any]],
    state: _TableState,
) -> None:
    for spec in _unique_specs(table):
        seen: dict[str, int] = {}
        for row in rows:
            if not _matches_partial(row, spec.where):
                continue
            key = tuple(row[column] for column in spec.columns)
            if not spec.nulls_not_distinct and any(value is None for value in key):
                continue
            key_sha256 = _key_sha256(key)
            seen[key_sha256] = seen.get(key_sha256, 0) + 1
        for key_sha256, duplicate_count in sorted(seen.items()):
            if duplicate_count > 1:
                state.duplicate_unique_keys.append(
                    (
                        f"{spec.name}: duplicate_count={duplicate_count} "
                        f"key_sha256={key_sha256}"
                    )
                )


def _validate_source_foreign_keys(
    rows_by_table: Mapping[str, list[dict[str, Any]]],
    states: Mapping[str, _TableState],
) -> None:
    for table in Base.metadata.sorted_tables:
        child_rows = rows_by_table[table.name]
        state = states[table.name]
        for constraint in table.foreign_key_constraints:
            local_names = tuple(element.parent.name for element in constraint.elements)
            remote_table = constraint.elements[0].column.table
            remote_names = tuple(element.column.name for element in constraint.elements)
            parent_keys = {
                tuple(row[name] for name in remote_names)
                for row in rows_by_table[remote_table.name]
            }
            name = constraint.name or (
                f"fk_{table.name}_{'_'.join(local_names)}_to_{remote_table.name}"
            )
            orphan_counts: dict[str, int] = {}
            for row in child_rows:
                key = tuple(row[name] for name in local_names)
                if any(value is None for value in key):
                    continue
                if key not in parent_keys:
                    key_sha256 = _key_sha256(key)
                    orphan_counts[key_sha256] = orphan_counts.get(key_sha256, 0) + 1
            for key_sha256, orphan_count in sorted(orphan_counts.items()):
                state.orphan_foreign_keys.append(
                    f"table={table.name} constraint={name} "
                    f"orphan_count={orphan_count} key_sha256={key_sha256}"
                )


def _decimal_total(rows: list[dict[str, Any]], column_name: str) -> Decimal:
    total = Decimal(0)
    for row in rows:
        value = row[column_name]
        if value is None:
            continue
        try:
            total += Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"invalid Decimal value in {column_name}") from exc
    return total


def _decimal_string(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _new_states() -> dict[str, _TableState]:
    return {
        table.name: _TableState(table)
        for table in Base.metadata.sorted_tables
    }


def _load_source_rows(
    source_path: Path,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, _TableState],
    dict[str, Decimal],
]:
    rows_by_table: dict[str, list[dict[str, Any]]] = {
        table.name: [] for table in Base.metadata.sorted_tables
    }
    states = _new_states()

    with closing(_readonly_sqlite(source_path)) as source_connection:
        integrity, _page_count = _sqlite_evidence(source_connection)
        if integrity != "ok":
            raise MigrationError("SQLite source integrity_check did not return ok")
        source_connection.row_factory = sqlite3.Row
        available_tables = _source_table_names(source_connection)

        for table in Base.metadata.sorted_tables:
            table_name = table.name
            state = states[table_name]
            if table_name not in available_tables:
                if table_name not in OPTIONAL_INTEGRATION_TABLES:
                    state.json_errors.append("schema: missing required source table")
                continue

            source_columns = _source_columns(source_connection, table_name)
            source_column_set = set(source_columns)
            target_column_set = set(table.columns.keys())
            missing_columns = sorted(target_column_set - source_column_set)
            unknown_columns = sorted(source_column_set - target_column_set)
            schema_fingerprint = _source_schema_fingerprint(
                source_connection, table_name
            )
            approved_adapter_columns: set[str] = set()

            for column_name in missing_columns:
                adapter = LEGACY_COLUMN_ADAPTERS.get((table_name, column_name))
                if adapter is None:
                    state.json_errors.append(
                        f"schema: missing current column {column_name!r} without adapter"
                    )
                elif adapter.source_schema_sha256 != schema_fingerprint:
                    state.json_errors.append(
                        f"schema: adapter fingerprint mismatch for {column_name!r}; "
                        f"source={schema_fingerprint}"
                    )
                else:
                    approved_adapter_columns.add(column_name)
            for column_name in unknown_columns:
                if (table_name, column_name) not in LEGACY_IGNORED_COLUMNS:
                    state.json_errors.append(
                        f"schema: unknown source column {column_name!r} without reconciliation"
                    )

            quoted_table = _quote_sqlite_identifier(table_name)
            try:
                raw_rows = source_connection.execute(
                    f"SELECT * FROM {quoted_table}"
                ).fetchall()
            except sqlite3.Error as exc:
                raise MigrationError(
                    f"SQLite source table {table_name!r} could not be read"
                ) from exc
            state.source_rows = len(raw_rows)

            converted_rows: list[dict[str, Any]] = []
            for row_number, raw_row in enumerate(raw_rows, start=1):
                safe_row = dict(raw_row)
                immutable_row = MappingProxyType(dict(safe_row))
                converted: dict[str, Any] = {}
                for column in table.columns:
                    if column.name in source_column_set:
                        raw_value = safe_row[column.name]
                    else:
                        adapter = (
                            LEGACY_COLUMN_ADAPTERS.get((table_name, column.name))
                            if column.name in approved_adapter_columns
                            else None
                        )
                        if adapter is None:
                            converted[column.name] = None
                            continue
                        try:
                            raw_value = adapter.derive(immutable_row)
                        except Exception:
                            state.json_errors.append(
                                f"schema: adapter for {column.name!r} failed at row {row_number}"
                            )
                            converted[column.name] = None
                            continue
                        state.synthesized_columns[column.name] = (
                            state.synthesized_columns.get(column.name, 0) + 1
                        )
                    try:
                        converted[column.name] = _convert_source_value(
                            column, raw_value
                        )
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        category = "JSON" if isinstance(column.type, JSON) else "value"
                        state.json_errors.append(
                            f"{category}: row {row_number} column {column.name!r}: {exc}"
                        )
                        converted[column.name] = None
                converted_rows.append(converted)
            rows_by_table[table_name] = converted_rows

    for table in Base.metadata.sorted_tables:
        _validate_source_uniques(table, rows_by_table[table.name], states[table.name])
    _validate_source_foreign_keys(rows_by_table, states)

    amount_totals: dict[str, Decimal] = {}
    for table_name, column_names in AMOUNT_COLUMNS.items():
        for column_name in column_names:
            key = f"{table_name}.{column_name}"
            try:
                amount_totals[key] = _decimal_total(
                    rows_by_table[table_name], column_name
                )
            except ValueError as exc:
                states[table_name].json_errors.append(f"amount: {exc}")
                amount_totals[key] = Decimal(0)
    return rows_by_table, states, amount_totals


def _reports(states: Mapping[str, _TableState]) -> tuple[TableMigrationReport, ...]:
    return tuple(states[table.name].report() for table in Base.metadata.sorted_tables)


def _migration_report(
    *,
    source_path: Path,
    snapshot: BackupReport,
    retained: bool,
    applied: bool,
    states: Mapping[str, _TableState],
    amount_totals: Mapping[str, Decimal],
    ok: bool,
    warnings: tuple[str, ...] = (),
) -> MigrationReport:
    evidence = SnapshotEvidence(
        source_path=snapshot.source_path,
        source_size=snapshot.source_size,
        source_sha256=snapshot.source_sha256,
        source_database_sha256=snapshot.source_database_sha256,
        source_wal_path=snapshot.source_wal_path,
        source_wal_size=snapshot.source_wal_size,
        source_wal_sha256=snapshot.source_wal_sha256,
        source_integrity_check=snapshot.source_integrity_check,
        source_page_count=snapshot.source_page_count,
        snapshot_path=snapshot.backup_path if retained else None,
        snapshot_size=snapshot.backup_size,
        snapshot_sha256=snapshot.backup_sha256,
        snapshot_integrity_check=snapshot.backup_integrity_check,
        snapshot_page_count=snapshot.backup_page_count,
        retained=retained,
        ok=snapshot.ok,
    )
    return MigrationReport(
        source_path=source_path,
        source_sha256=snapshot.source_sha256,
        backup_path=snapshot.backup_path if retained else None,
        backup_sha256=snapshot.backup_sha256 if retained else None,
        applied=applied,
        tables=_reports(states),
        amount_totals={
            key: _decimal_string(value)
            for key, value in sorted(amount_totals.items())
        },
        ok=ok,
        snapshot=evidence,
        warnings=warnings,
    )


def _states_have_errors(states: Mapping[str, _TableState]) -> bool:
    return any(state.has_errors for state in states.values())


def _assert_target_preconditions(connection: Connection) -> None:
    try:
        expected_head = ScriptDirectory.from_config(alembic_config).get_current_head()
        current_head = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
    except Exception:
        raise MigrationError("Target is not at Alembic head") from None
    if not expected_head or current_head != expected_head:
        raise MigrationError("Target is not at Alembic head")

    try:
        target_tables = set(inspect(connection).get_table_names())
        missing_tables = set(Base.metadata.tables) - target_tables
        if missing_tables:
            raise MigrationError("Target is not at Alembic head")
        nonempty = [
            table.name
            for table in Base.metadata.sorted_tables
            if connection.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
        ]
    except MigrationError:
        raise
    except SQLAlchemyError:
        raise MigrationError("Target emptiness could not be verified") from None
    if nonempty:
        raise MigrationError(
            "Target is not empty across all current metadata tables: "
            + ", ".join(nonempty)
        )


def _validate_target_uniques(
    connection: Connection,
    table: Any,
    state: _TableState,
) -> None:
    for spec in _unique_specs(table):
        columns = [table.c[name] for name in spec.columns]
        statement = (
            select(*columns, func.count().label("duplicate_count"))
            .select_from(table)
            .group_by(*columns)
            .having(func.count() > 1)
        )
        conditions = []
        if spec.where is not None:
            conditions.append(spec.where)
        if not spec.nulls_not_distinct:
            conditions.extend(column.is_not(None) for column in columns)
        if conditions:
            statement = statement.where(and_(*conditions))
        for duplicate in connection.execute(statement):
            key = tuple(duplicate[index] for index in range(len(columns)))
            description = _describe_key(
                spec.name,
                key,
                duplicate_count=int(duplicate.duplicate_count),
            )
            if description not in state.duplicate_unique_keys:
                state.duplicate_unique_keys.append(description)


def _validate_target_foreign_keys(
    connection: Connection,
    table: Any,
    state: _TableState,
) -> None:
    for constraint in table.foreign_key_constraints:
        local_columns = [element.parent for element in constraint.elements]
        remote_columns = [element.column for element in constraint.elements]
        parent_table = remote_columns[0].table
        parent_exists = exists(
            select(1)
            .select_from(parent_table)
            .where(
                and_(
                    *(
                        remote == local
                        for local, remote in zip(local_columns, remote_columns)
                    )
                )
            )
        )
        statement = (
            select(*local_columns, func.count().label("orphan_count"))
            .where(
                and_(
                    *(column.is_not(None) for column in local_columns),
                    ~parent_exists,
                )
            )
            .group_by(*local_columns)
        )
        name = constraint.name or (
            f"fk_{table.name}_{'_'.join(column.name for column in local_columns)}"
            f"_to_{parent_table.name}"
        )
        for orphan in connection.execute(statement):
            key = tuple(orphan[index] for index in range(len(local_columns)))
            description = (
                f"table={table.name} constraint={name} "
                f"orphan_count={int(orphan.orphan_count)} "
                f"key_sha256={_key_sha256(key)}"
            )
            if description not in state.orphan_foreign_keys:
                state.orphan_foreign_keys.append(description)


def _validate_target_json(
    connection: Connection,
    table: Any,
    state: _TableState,
) -> None:
    primary_keys = list(table.primary_key.columns)
    for column in table.columns:
        if not isinstance(column.type, JSON):
            continue
        dialect_type = column.type.dialect_impl(connection.dialect)
        json_kind = (
            func.jsonb_typeof(column)
            if isinstance(dialect_type, JSONB)
            else func.json_typeof(column)
        )
        errors: dict[str, list[tuple[Any, ...]]] = {}
        selected = [
            *primary_keys,
            column,
            column.is_(None).label("is_sql_null"),
            json_kind.label("json_kind"),
        ]
        for row in connection.execute(select(*selected)):
            value = row[len(primary_keys)]
            is_sql_null = bool(row[len(primary_keys) + 1])
            json_kind = row[len(primary_keys) + 2]
            if is_sql_null:
                if not column.nullable:
                    identity = tuple(
                        row[index] for index in range(len(primary_keys))
                    )
                    errors.setdefault("forbidden_sql_null", []).append(identity)
                continue
            if json_kind == "null":
                continue
            if json_kind is None:
                identity = tuple(row[index] for index in range(len(primary_keys)))
                errors.setdefault("missing_postgresql_json_type", []).append(
                    identity
                )
                continue
            try:
                json.dumps(value, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError):
                identity = tuple(row[index] for index in range(len(primary_keys)))
                errors.setdefault("non_serializable_json", []).append(identity)
        for error, identities in sorted(errors.items()):
            state.json_errors.append(
                f"JSON: table={table.name} column={column.name} error={error} "
                f"error_count={len(identities)} "
                f"key_sha256={_key_set_sha256(identities)}"
            )


def _validate_target(
    connection: Connection,
    states: Mapping[str, _TableState],
    source_amount_totals: Mapping[str, Decimal],
) -> dict[str, Decimal]:
    target_amount_totals: dict[str, Decimal] = {}
    for table in Base.metadata.sorted_tables:
        state = states[table.name]
        state.target_rows = connection.execute(
            select(func.count()).select_from(table)
        ).scalar_one()
        if state.target_rows != state.source_rows:
            state.json_errors.append(
                f"count: source={state.source_rows} target={state.target_rows}"
            )
        _validate_target_json(connection, table, state)
        _validate_target_uniques(connection, table, state)
        _validate_target_foreign_keys(connection, table, state)

    for table_name, column_names in AMOUNT_COLUMNS.items():
        table = Base.metadata.tables[table_name]
        for column_name in column_names:
            key = f"{table_name}.{column_name}"
            rows = [
                {column_name: value}
                for value in connection.execute(select(table.c[column_name])).scalars()
            ]
            try:
                target_total = _decimal_total(rows, column_name)
            except ValueError as exc:
                states[table_name].json_errors.append(f"amount: target {exc}")
                target_total = Decimal(0)
            target_amount_totals[key] = target_total
            if target_total != source_amount_totals[key]:
                states[table_name].json_errors.append(
                    "amount: "
                    f"{column_name} source={_decimal_string(source_amount_totals[key])} "
                    f"target={_decimal_string(target_total)}"
                )
    return target_amount_totals


def _advance_integer_sequences(connection: Connection) -> None:
    preparer = connection.dialect.identifier_preparer
    for table in Base.metadata.sorted_tables:
        primary_key = table.autoincrement_column
        if primary_key is None or not isinstance(primary_key.type, Integer):
            continue
        quoted_table = preparer.quote_identifier(table.name)
        if table.schema:
            quoted_table = (
                f"{preparer.quote_identifier(table.schema)}.{quoted_table}"
            )
        sequence = connection.execute(
            select(func.pg_get_serial_sequence(quoted_table, primary_key.name))
        ).scalar_one_or_none()
        if not sequence:
            continue
        maximum = connection.execute(select(func.max(primary_key))).scalar_one()
        connection.execute(
            text(
                "SELECT setval(CAST(:sequence AS regclass), :value, :is_called)"
            ),
            {
                "sequence": sequence,
                "value": int(maximum) if maximum is not None else 1,
                "is_called": maximum is not None,
            },
        )


def migrate_sqlite_to_postgres(
    *,
    source: Path,
    target_url: str,
    apply: bool,
) -> MigrationReport:
    """Copy and validate SQLite data in one PostgreSQL transaction.

    A dry run executes the exact copy and validation path, then explicitly rolls
    back. Apply creates a new SQLite backup first and commits only after every
    validation succeeds.
    """

    source_path = _resolve_sqlite_source(source)
    initial_source_sha256 = _sqlite_state(source_path).sha256
    try:
        parsed_target = make_url(target_url)
    except Exception:
        raise MigrationError("Target database URL is invalid") from None
    if parsed_target.get_backend_name() != "postgresql":
        raise MigrationError("Target database must be PostgreSQL")

    try:
        target_engine = create_engine(target_url, pool_pre_ping=True)
    except Exception:
        raise MigrationError("Target database could not be prepared") from None

    connection: Connection | None = None
    transaction = None
    snapshot_report: BackupReport | None = None
    snapshot_temp: TemporaryDirectory[str] | None = None
    source_guard: sqlite3.Connection | None = None
    states = _new_states()
    source_amount_totals: dict[str, Decimal] = {
        f"{table_name}.{column_name}": Decimal(0)
        for table_name, column_names in AMOUNT_COLUMNS.items()
        for column_name in column_names
    }
    try:
        try:
            connection = target_engine.connect()
            transaction = connection.begin()
        except Exception:
            raise MigrationError("Target database could not be opened safely") from None

        _assert_target_preconditions(connection)

        if apply:
            snapshot_report = backup_sqlite_source(source_path)
            if not snapshot_report.ok:
                states[Base.metadata.sorted_tables[0].name].json_errors.append(
                    "backup: SQLite source and backup evidence did not reconcile"
                )
            if snapshot_report.source_sha256 != initial_source_sha256:
                states[Base.metadata.sorted_tables[0].name].json_errors.append(
                    "backup: source state changed before verified snapshot"
                )
            snapshot_path = snapshot_report.backup_path
            try:
                source_guard = _lock_sqlite_source(source_path)
            except MigrationError:
                states[Base.metadata.sorted_tables[0].name].json_errors.append(
                    "source: write lock could not be acquired"
                )
            if source_guard is not None and not _locked_source_matches_snapshot(
                source_guard,
                source_path,
                snapshot_path,
                snapshot_report,
            ):
                states[Base.metadata.sorted_tables[0].name].json_errors.append(
                    "source: live state changed before source lock"
                )
        else:
            snapshot_temp = TemporaryDirectory(prefix="facai-sqlite-dry-run-")
            snapshot_path = Path(snapshot_temp.name) / "verified-source.db"
            snapshot_report = _backup_sqlite_to_path(source_path, snapshot_path)
            if not snapshot_report.ok:
                states[Base.metadata.sorted_tables[0].name].json_errors.append(
                    "snapshot: SQLite source changed while dry-run snapshot was created"
                )
            if snapshot_report.source_sha256 != initial_source_sha256:
                states[Base.metadata.sorted_tables[0].name].json_errors.append(
                    "snapshot: source state changed before dry-run copy"
                )

        if snapshot_report is None:
            raise MigrationError("Verified SQLite snapshot was not created")
        if _states_have_errors(states):
            transaction.rollback()
            return _migration_report(
                source_path=source_path,
                snapshot=snapshot_report,
                retained=apply,
                applied=False,
                states=states,
                amount_totals=source_amount_totals,
                ok=False,
            )

        rows_by_table, states, source_amount_totals = _load_source_rows(snapshot_path)
        if apply:
            if source_guard is None or not _locked_source_matches_snapshot(
                source_guard,
                source_path,
                snapshot_path,
                snapshot_report,
            ):
                states[Base.metadata.sorted_tables[0].name].json_errors.append(
                    "source: locked state changed after verified snapshot"
                )
        elif _sqlite_state(source_path).sha256 != snapshot_report.source_sha256:
            states[Base.metadata.sorted_tables[0].name].json_errors.append(
                "source: main/WAL state changed after verified snapshot"
            )

        if _states_have_errors(states):
            transaction.rollback()
            return _migration_report(
                source_path=source_path,
                snapshot=snapshot_report,
                retained=apply,
                applied=False,
                states=states,
                amount_totals=source_amount_totals,
                ok=False,
            )

        current_table_name = Base.metadata.sorted_tables[0].name
        try:
            for table in Base.metadata.sorted_tables:
                current_table_name = table.name
                rows = rows_by_table[table.name]
                for offset in range(0, len(rows), BATCH_SIZE):
                    connection.execute(
                        table.insert(),
                        rows[offset : offset + BATCH_SIZE],
                    )
            _validate_target(connection, states, source_amount_totals)
        except SQLAlchemyError:
            states[current_table_name].json_errors.append(
                "target: insert or validation failed"
            )
            transaction.rollback()
            for state in states.values():
                state.target_rows = 0
            return _migration_report(
                source_path=source_path,
                snapshot=snapshot_report,
                retained=apply,
                applied=False,
                states=states,
                amount_totals=source_amount_totals,
                ok=False,
            )

        if apply:
            if source_guard is None or not _locked_source_matches_snapshot(
                source_guard,
                source_path,
                snapshot_path,
                snapshot_report,
            ):
                states[Base.metadata.sorted_tables[0].name].json_errors.append(
                    "source: locked state changed during target copy"
                )
        elif _sqlite_state(source_path).sha256 != snapshot_report.source_sha256:
            states[Base.metadata.sorted_tables[0].name].json_errors.append(
                "source: main/WAL state changed during target copy"
            )
        if _states_have_errors(states):
            transaction.rollback()
            return _migration_report(
                source_path=source_path,
                snapshot=snapshot_report,
                retained=apply,
                applied=False,
                states=states,
                amount_totals=source_amount_totals,
                ok=False,
            )

        if apply:
            sequence_warnings = (SEQUENCE_SIDE_EFFECT_WARNING,)
            try:
                _advance_integer_sequences(connection)
                if source_guard is None or not _locked_source_matches_snapshot(
                    source_guard,
                    source_path,
                    snapshot_path,
                    snapshot_report,
                ):
                    states[Base.metadata.sorted_tables[0].name].json_errors.append(
                        "source: locked state changed during sequence stage"
                    )
                    transaction.rollback()
                    for state in states.values():
                        state.target_rows = 0
                    return _migration_report(
                        source_path=source_path,
                        snapshot=snapshot_report,
                        retained=True,
                        applied=False,
                        states=states,
                        amount_totals=source_amount_totals,
                        ok=False,
                        warnings=sequence_warnings,
                    )
                transaction.commit()
            except SQLAlchemyError:
                if transaction.is_active:
                    transaction.rollback()
                states[Base.metadata.sorted_tables[0].name].json_errors.append(
                    "target: sequence advancement failed"
                )
                for state in states.values():
                    state.target_rows = 0
                return _migration_report(
                    source_path=source_path,
                    snapshot=snapshot_report,
                    retained=True,
                    applied=False,
                    states=states,
                    amount_totals=source_amount_totals,
                    ok=False,
                    warnings=sequence_warnings,
                )
            applied = True
            warnings = sequence_warnings
        else:
            transaction.rollback()
            applied = False
            warnings = ()

        return _migration_report(
            source_path=source_path,
            snapshot=snapshot_report,
            retained=apply,
            applied=applied,
            states=states,
            amount_totals=source_amount_totals,
            ok=True,
            warnings=warnings,
        )
    except MigrationError:
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        raise
    except Exception:
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        raise MigrationError("Migration failed safely") from None
    finally:
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        try:
            if connection is not None:
                connection.close()
        finally:
            if source_guard is not None:
                try:
                    if source_guard.in_transaction:
                        source_guard.rollback()
                finally:
                    source_guard.close()
        target_engine.dispose()
        if snapshot_temp is not None:
            snapshot_temp.cleanup()


_SQLITE_HEADER = b"SQLite format 3\x00"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_state(path: Path) -> _SQLiteState:
    """Fingerprint all durable bytes that make up a SQLite committed state."""

    database_size = path.stat().st_size
    database_sha256 = _sha256(path)
    wal_candidate = Path(f"{path}-wal")
    if wal_candidate.is_file() and wal_candidate.stat().st_size > 0:
        wal_path: Path | None = wal_candidate
        wal_size = wal_candidate.stat().st_size
        wal_sha256: str | None = _sha256(wal_candidate)
        digest = hashlib.sha256()
        digest.update(b"facai-sqlite-state-v1\x00")
        digest.update(str(database_size).encode("ascii"))
        digest.update(b"\x00")
        digest.update(database_sha256.encode("ascii"))
        digest.update(b"\x00")
        digest.update(str(wal_size).encode("ascii"))
        digest.update(b"\x00")
        digest.update(wal_sha256.encode("ascii"))
        state_sha256 = digest.hexdigest()
    else:
        wal_path = None
        wal_size = 0
        wal_sha256 = None
        # Preserve the ordinary file SHA contract when no WAL participates.
        state_sha256 = database_sha256
    return _SQLiteState(
        database_size=database_size,
        database_sha256=database_sha256,
        wal_path=wal_path,
        wal_size=wal_size,
        wal_sha256=wal_sha256,
        sha256=state_sha256,
    )


def _resolve_sqlite_source(source: Path) -> Path:
    resolved = Path(source).expanduser().resolve()
    if not resolved.is_file():
        raise MigrationError("SQLite source does not exist or is not a regular file")
    try:
        with resolved.open("rb") as stream:
            header = stream.read(len(_SQLITE_HEADER))
    except OSError as exc:
        raise MigrationError("SQLite source cannot be read") from exc
    if header != _SQLITE_HEADER:
        raise MigrationError("Source is not a SQLite database")
    return resolved


def _readonly_sqlite(path: Path) -> sqlite3.Connection:
    encoded = quote(path.as_posix(), safe="/:")
    try:
        connection = sqlite3.connect(
            f"file:{encoded}?mode=ro",
            uri=True,
            timeout=5.0,
        )
        connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error as exc:
        raise MigrationError("SQLite source cannot be opened read-only") from exc


def _lock_sqlite_source(path: Path) -> sqlite3.Connection:
    """Reserve the live source for apply, then make the guard self-read-only."""

    encoded = quote(path.as_posix(), safe="/:")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"file:{encoded}?mode=rw",
            uri=True,
            timeout=5.0,
        )
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error as exc:
        if connection is not None:
            try:
                if connection.in_transaction:
                    connection.rollback()
            finally:
                connection.close()
        raise MigrationError("SQLite source write lock could not be acquired") from exc


def _sqlite_logical_sha256(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    digest.update(b"facai-sqlite-logical-v1\x00")
    for statement in connection.iterdump():
        encoded = statement.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _locked_source_matches_snapshot(
    source_guard: sqlite3.Connection,
    source_path: Path,
    snapshot_path: Path,
    snapshot: BackupReport,
) -> bool:
    try:
        if not source_guard.in_transaction:
            return False
        if int(source_guard.execute("PRAGMA query_only").fetchone()[0]) != 1:
            return False
        live_state = _sqlite_state(source_path)
        source_integrity, source_pages = _sqlite_evidence(source_guard)
        source_logical_sha256 = _sqlite_logical_sha256(source_guard)
        with closing(_readonly_sqlite(snapshot_path)) as snapshot_connection:
            snapshot_integrity, snapshot_pages = _sqlite_evidence(
                snapshot_connection
            )
            snapshot_logical_sha256 = _sqlite_logical_sha256(snapshot_connection)
        return (
            live_state.database_size == snapshot.source_size
            and live_state.database_sha256 == snapshot.source_database_sha256
            and live_state.wal_path == snapshot.source_wal_path
            and live_state.wal_size == snapshot.source_wal_size
            and live_state.wal_sha256 == snapshot.source_wal_sha256
            and live_state.sha256 == snapshot.source_sha256
            and source_integrity == snapshot.source_integrity_check == "ok"
            and source_pages == snapshot.source_page_count
            and snapshot_path.stat().st_size == snapshot.backup_size
            and _sha256(snapshot_path) == snapshot.backup_sha256
            and snapshot_integrity == snapshot.backup_integrity_check == "ok"
            and snapshot_pages == snapshot.backup_page_count
            and source_logical_sha256 == snapshot_logical_sha256
        )
    except (OSError, sqlite3.Error):
        return False


def _sqlite_evidence(connection: sqlite3.Connection) -> tuple[str, int]:
    try:
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    except sqlite3.Error as exc:
        raise MigrationError("SQLite integrity evidence could not be collected") from exc
    integrity = "\n".join(str(row[0]) for row in integrity_rows)
    return integrity, page_count


def _backup_sqlite_to_path(source_path: Path, backup_path: Path) -> BackupReport:
    rollback_journal = Path(f"{source_path}-journal")
    if rollback_journal.is_file() and rollback_journal.stat().st_size:
        raise MigrationError(
            "SQLite source has an active rollback journal; stop all writers first"
        )
    state_before = _sqlite_state(source_path)
    try:
        with closing(_readonly_sqlite(source_path)) as source_connection:
            source_connection.execute("BEGIN")
            source_integrity, source_pages = _sqlite_evidence(source_connection)
            with closing(sqlite3.connect(backup_path)) as backup_connection:
                source_connection.backup(backup_connection)
                backup_connection.commit()
                backup_integrity, backup_pages = _sqlite_evidence(backup_connection)
    except (OSError, sqlite3.Error) as exc:
        raise MigrationError("SQLite backup could not be created safely") from exc

    state_after = _sqlite_state(source_path)
    backup_size = backup_path.stat().st_size
    backup_sha256 = _sha256(backup_path)
    ok = (
        state_after.sha256 == state_before.sha256
        and source_integrity == "ok"
        and backup_integrity == "ok"
        and source_pages == backup_pages
    )
    return BackupReport(
        source_path=source_path,
        source_size=state_before.database_size,
        source_sha256=state_before.sha256,
        source_database_sha256=state_before.database_sha256,
        source_wal_path=state_before.wal_path,
        source_wal_size=state_before.wal_size,
        source_wal_sha256=state_before.wal_sha256,
        source_integrity_check=source_integrity,
        source_page_count=source_pages,
        backup_path=backup_path,
        backup_size=backup_size,
        backup_sha256=backup_sha256,
        backup_integrity_check=backup_integrity,
        backup_page_count=backup_pages,
        ok=ok,
    )


def backup_sqlite_source(source: Path) -> BackupReport:
    """Create and verify a consistent SQLite backup without mutating the source."""

    source_path = _resolve_sqlite_source(source)
    backup_dir = source_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"{source_path.stem}_pre_postgres_{stamp}.db"
    return _backup_sqlite_to_path(source_path, backup_path)
