# Ecommerce API Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有应用安全迁移到 PostgreSQL/Alembic 基线，并提供只保护 API 接入中心的管理员会话、凭证加密、应用配置、OAuth state 和公共回调边界。

**Architecture:** `database.py` 继续暴露现有 `engine`、`SessionLocal`、`Base`，但按方言创建引擎并让 PostgreSQL schema 只受 Alembic 管理。接入安全能力放入独立 `integrations` 包，不复活已经退役的全局 `services/security.py` 登录。所有秘密通过环境变量和 AES-GCM 信封处理，公开回调与内网管理路由分别注册。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2.0、PostgreSQL、Alembic 1.18.5、psycopg 3.3.4、cryptography 49.0、Pydantic 2、httpx、`unittest`。

## Global Constraints

- 本计划开始前必须有一个允许创建/删除表的空 PostgreSQL 测试库，并通过 `FACAI_TEST_DATABASE_URL` 提供；不得指向生产库。
- 保持 `services/security.py`、`routers/auth.py` 和 `/app/login` 的现有兼容行为，防止全局登录回归。
- `GET /app/api-connections/login` 与 `POST /api/integrations/session` 公开；其他 `/app/api-connections*` 页面未登录返回 303，其他 `/api/integrations*` 未登录返回 JSON 401。
- `/integrations/oauth/callback/{provider}` 与 `/integrations/events/{provider}` 不经过管理员会话，但必须分别经过 state 或平台签名验证。
- 生产 PostgreSQL 启动只验证 schema revision，不自动建表；SQLite 测试和回滚模式保留现有 `create_all` 与轻量兼容迁移。
- 安全测试不得写入真实 Secret/Token；固定夹具只使用明显的测试字串。

---

### Task 1: Pin Database And Cryptography Dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Test: `tests/test_integration_settings.py`

- [ ] **Step 1: Write the failing dependency and safe-example tests**

Create `tests/test_integration_settings.py` with assertions that `requirements.txt` contains exact pins and `.env.example` contains names but no usable secrets:

```python
class IntegrationDependencyContractTests(unittest.TestCase):
    def test_runtime_dependencies_are_pinned(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("alembic==1.18.5", requirements)
        self.assertIn("psycopg[binary]==3.3.4", requirements)
        self.assertIn("cryptography==49.0.0", requirements)

    def test_env_example_documents_integration_settings_without_secrets(self):
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        for key in (
            "FACAI_INTEGRATIONS_ADMIN_PASSWORD_HASH",
            "FACAI_INTEGRATIONS_SESSION_SECRET",
            "FACAI_INTEGRATIONS_MASTER_KEY",
            "FACAI_INTEGRATIONS_INTERNAL_BASE_URL",
            "FACAI_INTEGRATIONS_PUBLIC_BASE_URL",
            "FACAI_INTEGRATION_ARCHIVE_DIR",
            "FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS",
            "FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
        ):
            self.assertRegex(content, rf"(?m)^{key}=$")
```

- [ ] **Step 2: Run the test and verify the expected failure**

Run: `python -m unittest tests.test_integration_settings.IntegrationDependencyContractTests -v`

Expected: fails because the pins and integration environment names do not exist.

- [ ] **Step 3: Add exact pins and empty configuration names**

Append to `requirements.txt`:

```text
alembic==1.18.5
psycopg[binary]==3.3.4
cryptography==49.0.0
```

Append to `.env.example` with no values:

```dotenv
# Ecommerce API integration center (required only when this feature is configured)
FACAI_INTEGRATIONS_ADMIN_PASSWORD_HASH=
FACAI_INTEGRATIONS_SESSION_SECRET=
FACAI_INTEGRATIONS_MASTER_KEY=
FACAI_INTEGRATIONS_INTERNAL_BASE_URL=
FACAI_INTEGRATIONS_PUBLIC_BASE_URL=
FACAI_INTEGRATION_ARCHIVE_DIR=
FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS=
FACAI_DESTRUCTIVE_TEST_DATABASE_ACK=
FACAI_INTEGRATION_WORKER_CONCURRENCY=4
```

- [ ] **Step 4: Install and verify imports**

Run: `python -m pip install -r requirements.txt`

Run: `python -c "import alembic, cryptography, psycopg; print(alembic.__version__, cryptography.__version__, psycopg.__version__)"`

Expected: prints `1.18.5 49.0.0 3.3.4`.

- [ ] **Step 5: Run the target tests and commit**

Run: `python -m unittest tests.test_integration_settings.IntegrationDependencyContractTests tests.test_security_hardening -v`

Expected: pass, including existing safe-example-value tests.

Commit: `git add requirements.txt .env.example tests/test_integration_settings.py && git commit -m "build: add integration database and crypto dependencies"`

---

### Task 2: Make Database Engine Creation Dialect-Aware

**Files:**
- Modify: `database.py`
- Modify: `creator_models.py`
- Test: `tests/test_database_dialects.py`
- Test: `tests/test_sqlite_compat_migrations.py`
- Test: `tests/test_creator_migrations.py`

- [ ] **Step 1: Write failing engine-factory tests**

Create `tests/test_database_dialects.py`:

```python
class DatabaseDialectTests(unittest.TestCase):
    def test_sqlite_engine_keeps_thread_override(self):
        engine = database.create_database_engine("sqlite:///:memory:")
        self.assertEqual(engine.dialect.name, "sqlite")
        with engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(), 1)

    def test_postgres_engine_does_not_receive_sqlite_connect_args(self):
        with patch("database.create_engine") as create_engine:
            database.create_database_engine("postgresql+psycopg://u:p@db/facai")
        kwargs = create_engine.call_args.kwargs
        self.assertNotIn("connect_args", kwargs)
        self.assertTrue(kwargs["pool_pre_ping"])

    def test_postgres_init_does_not_create_or_patch_schema(self):
        postgres_engine = Mock()
        postgres_engine.dialect.name = "postgresql"
        with patch.object(database, "engine", postgres_engine), \
             patch.object(database.Base.metadata, "create_all") as create_all, \
             patch.object(database, "_ensure_compatible_columns") as patch_columns, \
             patch.object(database, "assert_schema_current") as assert_current:
            database.init_db()
        create_all.assert_not_called()
        patch_columns.assert_not_called()
        assert_current.assert_called_once_with(postgres_engine)
```

- [ ] **Step 2: Run and confirm the red state**

Run: `python -m unittest tests.test_database_dialects -v`

Expected: fails because `create_database_engine()` is absent and PostgreSQL `init_db()` still calls `create_all()`.

- [ ] **Step 3: Extract a dialect-aware factory**

Replace unconditional directory creation and engine construction in `database.py` with:

```python
def create_database_engine(url: str):
    options: dict[str, object] = {"pool_pre_ping": True}
    if url.startswith("sqlite:"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **options)


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw_path = url.removeprefix("sqlite:///")
    if raw_path == ":memory:":
        return
    Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent(DATABASE_URL)
engine = create_database_engine(DATABASE_URL)
```

Keep the existing connect event, but read the connection record's dialect through the module engine only after confirming it is SQLite.

- [ ] **Step 4: Register all current and future models, then stop PostgreSQL auto-DDL**

At the start of `init_db()` import `models`, `creator_models`, `integration_models`, and `commerce_models`. Immediately return for PostgreSQL:

```python
def init_db():
    import models
    import creator_models
    if engine.dialect.name != "sqlite":
        assert_schema_current(engine)
        return
    if _schema_migration_required():
        _backup_sqlite_database()
    Base.metadata.create_all(bind=engine)
    _ensure_creator_indexes()
    _ensure_compatible_columns()
    _ensure_creator_integrity_triggers()
```

Task 3 adds unconditional `integration_models` and `commerce_models` imports after creating those files. Implement `assert_schema_current(bind)` using `ScriptDirectory.from_config(alembic_config).get_current_head()`: read `alembic_version`, compare heads, and raise a startup error that prints `alembic upgrade head` without running it.

- [ ] **Step 5: Preserve current partial-unique semantics on PostgreSQL**

In `creator_models.py`, add matching `postgresql_where` expressions beside the existing `sqlite_where` for `uq_creators_platform_uid`, `uq_creators_douyin_handle`, `uq_creator_collaboration_external`, and `uq_creator_import_committed_file`. Extend `tests/test_database_dialects.py` to compile each index with the PostgreSQL dialect and assert its DDL contains `WHERE`.

- [ ] **Step 6: Run dialect and SQLite regression tests**

Run: `python -m unittest tests.test_database_dialects tests.test_sqlite_compat_migrations tests.test_creator_migrations -v`

Expected: all pass; legacy SQLite backup and trigger behavior remains unchanged.

- [ ] **Step 7: Commit the engine seam**

Commit: `git add database.py creator_models.py tests/test_database_dialects.py && git commit -m "refactor: make database startup dialect aware"`

---

### Task 3: Define Shared Types And Integration Control Models

**Files:**
- Create: `integrations/__init__.py`
- Create: `integrations/types.py`
- Create: `integration_models.py`
- Create: `commerce_models.py`
- Test: `tests/test_integration_models.py`

- [ ] **Step 1: Write failing enum and constraint tests**

Create `tests/test_integration_models.py` and use a temporary SQLite database for fast model-contract tests. Assert:

- `Provider` contains exactly `qianchuan`, `doudian`, `taobao`, `pdd`.
- `ConnectionStatus` contains exactly the eight approved states.
- `ConnectionType`, `AuthorizationStatus`, `ResourceType`, `SyncSource`, `SyncStatus`, `JobType`, `JobStatus`, `CheckpointStatus`, `CapabilityStage`, `ExportStatus` and all normalized business-status enums exactly match the program-level shared contract; no platform may extend them locally.
- duplicate `provider` app configs fail.
- duplicate `provider + connection_type + external_account_id` connections fail.
- duplicate OAuth state hashes fail.
- login throttle uniqueness is enforced by source fingerprint.
- a connection references an authorization and never has token or secret columns.
- timestamps are timezone-aware column types and credential columns are `Text` ciphertext fields.
- every persisted enum column has a deterministic named database CHECK constraint using the enum values (not Python member names); raw SQL with an invalid provider/connection/auth status/type is rejected on PostgreSQL.

Core test example:

```python
class IntegrationModelTests(unittest.TestCase):
    def test_connection_has_no_credential_columns(self):
        names = {column.name for column in IntegrationConnection.__table__.columns}
        self.assertFalse(names & {"access_token", "refresh_token", "app_secret", "token_ciphertext"})

    def test_provider_values_are_stable(self):
        self.assertEqual(
            [item.value for item in Provider],
            ["qianchuan", "doudian", "taobao", "pdd"],
        )
```

- [ ] **Step 2: Run and confirm the red state**

Run: `python -m unittest tests.test_integration_models -v`

Expected: import failure because types and models do not exist.

- [ ] **Step 3: Implement the shared enums and immutable transport records**

In `integrations/types.py`, define `JsonValue`, `Provider`, `ConnectionStatus`, `ConnectionType`, `AuthorizationStatus`, `ResourceType`, `SyncSource`, `SyncStatus`, `JobType`, `JobStatus`, `CheckpointStatus`, `CapabilityStage`, `ExportStatus`, the normalized business-status enums, `TokenBundle`, `AccountIdentity`, `Capability`, `CapabilityReport`, `ConnectionContext`, `RateLimitHint`, `TimeWindow`, `NormalizedRecord`, `FetchPage`, and `RevokeResult`. Use `str, Enum` for persisted/API values and frozen slotted dataclasses for connector values. Copy the exact persisted values and transitions from the program-level “Shared Domain Contracts”; `ResourceType` therefore includes `order_items` and all fifteen fixed values. `order_items` is emitted with an order fetch and is not independently scheduled.

The normalized status enums are fixed here so adapters cannot invent values:

```python
class OrderStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CLOSED = "closed"


class ProductStatus(str, Enum):
    UNKNOWN = "unknown"
    ON_SALE = "on_sale"
    OFF_SHELF = "off_shelf"
    DELETED = "deleted"


class AccountStatus(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    INACTIVE = "inactive"
    CLOSED = "closed"


class RefundStatus(str, Enum):
    UNKNOWN = "unknown"
    REQUESTED = "requested"
    PROCESSING = "processing"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CLOSED = "closed"


class ShipmentStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class SettlementStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    SETTLED = "settled"
    REVERSED = "reversed"


class FinanceTransactionStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class AdEntityStatus(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    DELETED = "deleted"
```

Every normalized business record type that carries status stores both `raw_status` and the corresponding normalized enum value.

- [ ] **Step 4: Implement the six control tables**

In `integration_models.py`, create:

| Model | Table | Required columns and constraints |
|---|---|---|
| `IntegrationAppConfig` | `integration_app_configs` | unique `provider`; `app_id`; nullable `app_secret_ciphertext` and safe `app_secret_tail`; `status`; UTC `created_at/updated_at` |
| `IntegrationAuthorization` | `integration_authorizations` | `provider`; unique `(provider, external_subject_id)`; `scopes` JSON; access/refresh token ciphertext plus safe four-character tails; access/refresh expiry; refresh lease owner/expiry; status; last authorized/refreshed timestamps |
| `IntegrationConnection` | `integration_connections` | FK authorization; provider; connection type; unique `(provider, connection_type, external_account_id)`; display name; status; capability report JSON; earliest available date; last successful sync; disabled timestamp |
| `IntegrationOAuthState` | `integration_oauth_states` | unique 64-char SHA-256 state hash; provider; initiating session digest; safe relative return path; expires/consumed timestamps |
| `IntegrationSecurityAudit` | `integration_security_audit` | event type; outcome; source/session digests; provider; target type/ID strings; summary code; allowlisted JSON details; UTC timestamp; intentionally no target FK so purge retains audit |
| `IntegrationLoginThrottle` | `integration_login_throttles` | unique source digest; failure count; window start; locked-until and updated timestamps; persistent across processes and restarts |

Use named constraints and indexes. Relationships must use `passive_deletes=True`; authorization→connections uses database `ON DELETE RESTRICT` so shared tokens cannot disappear while a connection exists.

Use one helper in `integrations/types.py` for every persisted enum:

```python
def persisted_enum(enum_type: type[Enum], *, name: str) -> sqlalchemy.Enum:
    return sqlalchemy.Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [item.value for item in cls],
    )
```

Constraint/type names follow `ck_<table>_<column>` and are explicitly passed per column so Alembic output is stable. Tests inspect every control-table enum column and execute representative raw invalid INSERT/UPDATE statements on PostgreSQL; Python validation alone is not accepted.

Use this timestamp helper consistently:

```python
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
```

Do not use `datetime.utcnow()`.

- [ ] **Step 5: Create an intentionally empty commerce model module**

Create `commerce_models.py` with a module docstring and import `Base`. Phase 2 will populate it and add revision `20260713_0002`; the empty module lets Alembic use a stable import list now.

Remove the temporary `ModuleNotFoundError` guard from `database.init_db()` and import both model modules unconditionally.

- [ ] **Step 6: Run tests and inspect metadata**

Run: `python -m unittest tests.test_integration_models tests.test_database_dialects -v`

Run: `python -c "import database, integration_models, commerce_models; print(sorted(t for t in database.Base.metadata.tables if t.startswith('integration_')))"`

Expected: exactly the six control tables are printed and tests pass.

- [ ] **Step 7: Commit the control schema**

Commit: `git add integrations integration_models.py commerce_models.py database.py tests/test_integration_models.py && git commit -m "feat: add integration control domain models"`

---

### Task 4: Introduce Alembic And A PostgreSQL Baseline

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/20260713_0001_postgres_baseline.py`
- Create: `integrations/db_safety.py`
- Create: `scripts/assert_disposable_postgres.py`
- Modify: `.gitignore`
- Test: `tests/test_postgres_safety.py`
- Test: `tests/test_alembic_postgres.py`

- [ ] **Step 1: Write a PostgreSQL-only migration test**

Create `tests/test_postgres_safety.py` and `tests/test_alembic_postgres.py`. Before any connect/drop/downgrade, the latter calls a shared destructive database guard rather than merely checking that a URL exists:

```python
TEST_URL = assert_disposable_postgres(
    url_env="FACAI_TEST_DATABASE_URL",
    acknowledgement_env="FACAI_DESTRUCTIVE_TEST_DATABASE_ACK",
)


class AlembicPostgresTests(unittest.TestCase):
    def test_upgrade_downgrade_upgrade_round_trip(self):
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", TEST_URL.replace("%", "%%"))
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        tables = set(inspect(create_engine(TEST_URL)).get_table_names())
        self.assertIn("products", tables)
        self.assertIn("creator_import_batches", tables)
        self.assertIn("integration_app_configs", tables)
        command.downgrade(config, "base")
        command.upgrade(config, "head")
```

`assert_disposable_postgres` validates before connecting: PostgreSQL/psycopg scheme only; explicit database component ending `_test` or `_ci`; acknowledgement value exactly equals the decoded database name; normalized host/port/database differs from `DATABASE_URL` and `FACAI_MIGRATION_TEST_DATABASE_URL`; username is present; query/fragment are rejected except an allowlisted SSL mode. After connecting, require `SELECT current_database()` equals the acknowledged name. It returns a redacted-safe URL object/string but never logs credentials. Unit tests prove missing/wrong ack, SQLite URL, production equality, bad suffix and server-name mismatch all fail before destructive work.

`scripts/assert_disposable_postgres.py --env FACAI_TEST_DATABASE_URL --ack-env FACAI_DESTRUCTIVE_TEST_DATABASE_ACK` exposes the same guard for every documented Alembic command and prints only database host/name plus `safe=true`.

Also add a source contract asserting `alembic/env.py` imports every model module before assigning `target_metadata`, and a PostgreSQL inspection contract asserting every fixed enum column has its expected named CHECK constraint after upgrade.

- [ ] **Step 2: Run and confirm the red state**

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL must reference the disposable PostgreSQL test database' }; python -m unittest tests.test_alembic_postgres -v`

Expected: fails because Alembic configuration does not exist.

- [ ] **Step 3: Implement the destructive guard and deterministic Alembic configuration**

Implement `integrations/db_safety.py` and its thin CLI first until `tests.test_postgres_safety` passes, then run: `alembic init alembic`

Edit `alembic.ini` so `sqlalchemy.url` is empty and log configuration remains local. In `alembic/env.py`, require the environment URL instead of committing credentials:

```python
from database import Base
import models
import creator_models
import integration_models
import commerce_models

target_metadata = Base.metadata


def database_url() -> str:
    value = os.getenv("FACAI_MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("FACAI_MIGRATION_DATABASE_URL or DATABASE_URL is required")
    return value


config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))
```

Configure `compare_type=True`, `compare_server_default=True`, and `transaction_per_migration=True` in online migrations.

- [ ] **Step 4: Generate an explicit baseline against an empty disposable database**

After Task 3 has created `integration_models.py` and `commerce_models.py` stubs registered in metadata, run:

```powershell
python scripts/assert_disposable_postgres.py --env FACAI_TEST_DATABASE_URL --ack-env FACAI_DESTRUCTIVE_TEST_DATABASE_ACK
$env:FACAI_MIGRATION_DATABASE_URL=$env:FACAI_TEST_DATABASE_URL
alembic downgrade base
alembic revision --autogenerate --rev-id 20260713_0001 -m "postgres baseline and integration control"
```

Rename the generated file to `alembic/versions/20260713_0001_postgres_baseline.py`, set `revision = "20260713_0001"` and `down_revision = None` explicitly. Review it and require explicit `op.create_table()`/`op.create_index()` operations; reject a migration that calls `Base.metadata.create_all()` or imports application models from `upgrade()`.

- [ ] **Step 5: Verify complete metadata coverage**

Add to the test:

```python
with engine.connect() as connection:
    context = MigrationContext.configure(connection)
    diff = compare_metadata(context, Base.metadata)
self.assertEqual(diff, [])
```

Run: `if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL must reference the disposable PostgreSQL test database' }; python -m unittest tests.test_alembic_postgres -v`

Expected: round-trip and metadata comparison pass.

- [ ] **Step 6: Prevent local migration artifacts from being committed**

Add `.pytest_cache/`, `alembic/__pycache__/`, and `alembic/versions/__pycache__/` only if not already covered. Do not ignore migration revision files.

- [ ] **Step 7: Commit the baseline**

Commit: `git add alembic.ini alembic integrations/db_safety.py scripts/assert_disposable_postgres.py .gitignore tests/test_postgres_safety.py tests/test_alembic_postgres.py && git commit -m "feat: add guarded PostgreSQL Alembic baseline"`

---

### Task 5: Build A Verified SQLite-To-PostgreSQL Migration Command

**Files:**
- Create: `integrations/migration.py`
- Create: `scripts/migrate_sqlite_to_postgres.py`
- Create: `docs/runbooks/postgres-cutover.md`
- Test: `tests/test_sqlite_to_postgres_migration.py`

- [ ] **Step 1: Write failing report and safety tests**

Create tests for these observable contracts:

```python
@dataclass(frozen=True, slots=True)
class TableMigrationReport:
    table: str
    source_rows: int
    target_rows: int
    orphan_foreign_keys: tuple[str, ...]
    duplicate_unique_keys: tuple[str, ...]
    json_errors: tuple[str, ...]
    synthesized_columns: Mapping[str, int]


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
```

The tests must prove:

- a missing/non-SQLite source is rejected;
- a target not at Alembic head is rejected;
- a non-empty target is rejected before copy;
- `dry_run=True` inserts and validates inside one transaction, then rolls it back;
- `apply=True` creates a consistent SQLite backup first and commits only if every validation passes;
- a deliberately broken JSON value or orphan FK returns `ok=False` and leaves the target empty;
- sequences advance past migrated integer primary keys.
- a source table missing a current column fails closed unless an explicit, version-tested `LegacyColumnAdapter` supplies it; the report counts every synthesized column and the source hash remains unchanged.

- [ ] **Step 2: Run against the disposable PostgreSQL database and verify red**

Run:

```powershell
if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL must reference the disposable PostgreSQL test database' }
python scripts/assert_disposable_postgres.py --env FACAI_TEST_DATABASE_URL --ack-env FACAI_DESTRUCTIVE_TEST_DATABASE_ACK
python -m unittest tests.test_sqlite_to_postgres_migration -v
```

Expected: import failure because `integrations.migration` and the CLI are absent.

- [ ] **Step 3: Implement topologically ordered copying**

Implement `migrate_sqlite_to_postgres(*, source: Path, target_url: str, apply: bool) -> MigrationReport` with the transaction algorithm below.

Use a read-only SQLite engine and a PostgreSQL transaction. Iterate `Base.metadata.sorted_tables`; inspect each SQLite table/column set first and select only source columns that actually exist, rather than issuing a current-metadata SELECT against an older schema. Convert JSON text through each target column's SQLAlchemy type and insert batches of 500 with the target table's `insert()`. All legacy revision-0001 business tables are required, while integration/commerce tables absent from an older SQLite source are reported as `0 -> 0` and left empty. Never disable target foreign keys.

Define a small allowlisted `LegacyColumnAdapter` registry keyed by `(table_name, missing_column)`. An adapter receives only the already-read safe row mapping and returns a deterministic derived value; it cannot query or mutate the source. Any missing required column without an adapter aborts before target insert. Unexpected source-only columns also abort unless an explicit `LegacyIgnoredColumn` entry documents why the value is obsolete and how its row/count is reconciled; silently dropping unknown columns is forbidden. Tests fingerprint representative historical SQLite schemas, prove unknown drift fails, and prove adding a future registered adapter does not change source bytes/SHA-256.

Target emptiness is evaluated across every current metadata table. Dry-run performs the same inserts and validation as apply, records the in-transaction counts, and explicitly rolls back.

- [ ] **Step 4: Implement deterministic validations**

For every table compare source/target counts, parse every JSON/JSONB value, query every declared unique constraint/index for duplicates, and query every FK for missing parent rows. Compare `Decimal` totals as strings for:

```python
AMOUNT_COLUMNS = {
    "qianchuan_material_performance": (
        "transaction_amount",
        "user_pay_amount",
        "spend",
    ),
    "creator_collaborations": ("actual_paid_cents",),
}
```

For every integer auto-increment PK on apply, obtain `pg_get_serial_sequence` with quoted SQLAlchemy identifiers. If rows exist, call `setval(sequence, max(id), true)`; if empty, call `setval(sequence, 1, false)`; skip columns without a sequence. Do not construct unquoted identifiers from CLI input.

- [ ] **Step 5: Implement consistent backup and CLI behavior**

Implement `backup_sqlite_source(source: Path) -> BackupReport` with Python's SQLite backup API. It creates a name such as `data/backups/script_agent_pre_postgres_20260713T013000Z.db`, hashes source and backup with SHA-256, compares SQLite integrity/page counts, and includes both paths, sizes and hashes in the report. `--apply` always calls the same function again immediately before copying, even if a prior preflight backup exists. The CLI accepts exactly:

```text
--source PATH
--target-env ENVIRONMENT_VARIABLE_NAME  # required by dry-run/apply only
--backup-only | --dry-run | --apply
```

`--backup-only` never opens a target database and produces the operator's preflight backup before target preparation. `--target-env` is a variable name, never a URL. Print UTF-8 JSON with all reports. Exit 0 only when `report.ok` is true; otherwise exit 1. Never edit `.env` or `DATABASE_URL`.

- [ ] **Step 6: Add the operator runbook**

Document preflight, stop-writes, SQLite SHA-256, Alembic upgrade, dry-run, apply, row/amount/FK/JSON review, read-only URL switch, smoke tests, point-of-no-return and recovery. SQLite rollback is allowed only while the new app uses a read-only PostgreSQL role, worker/traffic are disabled and post-migration row/timestamp evidence proves zero writes. After opening PostgreSQL writes, recovery must use PostgreSQL backup/PITR or a forward fix; never copy PostgreSQL changes back into SQLite.

- [ ] **Step 7: Run focused tests and a CLI smoke test**

Run:

```powershell
if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL must reference the disposable PostgreSQL test database' }
python scripts/assert_disposable_postgres.py --env FACAI_TEST_DATABASE_URL --ack-env FACAI_DESTRUCTIVE_TEST_DATABASE_ACK
python -m unittest tests.test_sqlite_to_postgres_migration tests.test_alembic_postgres -v
python scripts/migrate_sqlite_to_postgres.py --source .\data\script_agent.db --backup-only
python scripts/migrate_sqlite_to_postgres.py --source .\data\script_agent.db --target-env FACAI_TEST_DATABASE_URL --dry-run
```

Expected: tests pass; backup-only emits matching source/backup integrity evidence without opening PostgreSQL; dry-run emits `"ok": true`, `"applied": false`; target tables remain empty after dry-run.

- [ ] **Step 8: Commit migration tooling**

Commit: `git add integrations/migration.py scripts/migrate_sqlite_to_postgres.py docs/runbooks/postgres-cutover.md tests/test_sqlite_to_postgres_migration.py && git commit -m "feat: add verified SQLite to PostgreSQL migration"`

---

### Task 6: Validate Security Settings And Encrypt Credentials

**Files:**
- Create: `integrations/settings.py`
- Create: `integrations/crypto.py`
- Create: `integrations/redaction.py`
- Create: `scripts/generate_integration_secrets.py`
- Modify: `config.py`
- Modify: `services/runtime_logging.py`
- Test: `tests/test_integration_settings.py`
- Test: `tests/test_integration_crypto.py`
- Test: `tests/test_integration_redaction.py`

- [ ] **Step 1: Write failing configuration and cryptography tests**

Test all of the following:

- missing values produce `ready=False` and a stable list of missing keys without breaking imports;
- master key is URL-safe Base64 and decodes to exactly 32 bytes;
- session secret decodes to at least 32 bytes;
- internal and public base URLs are origin-only URLs with empty path/query/fragment and HTTPS, except `http://localhost[:port]` and loopback development URLs; their production hostnames must differ;
- archive path must be absolute and is not created during pure settings validation;
- trusted proxy CIDRs are empty or a comma-separated set of canonical IPv4/IPv6 networks; hostnames, malformed CIDRs and catch-all `0.0.0.0/0`/`::/0` are rejected;
- AES-GCM round-trip works; tampered nonce/ciphertext/tag and wrong purpose fail closed;
- buyer HMAC is deterministic, differs from ciphertext, and uses a derived key;
- redaction removes sensitive keys recursively and raises if a normalized/archive payload still contains a banned key;
- uvicorn access logging redacts OAuth `code/state` and credential-like query values before handlers format or persist the record.

- [ ] **Step 2: Run the tests and verify red**

Run: `python -m unittest tests.test_integration_settings tests.test_integration_crypto tests.test_integration_redaction -v`

Expected: module import failures.

- [ ] **Step 3: Implement immutable settings with separate readiness levels**

In `integrations/settings.py`:

```python
@dataclass(frozen=True, slots=True)
class IntegrationSettings:
    admin_password_hash: str | None
    session_secret: bytes | None
    master_key: bytes | None
    internal_base_url: str | None
    public_base_url: str | None
    archive_dir: Path | None
    trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...]
    worker_concurrency: int
    login_ready: bool
    credential_ready: bool
    errors: tuple[str, ...]


def load_integration_settings(
    environ: Mapping[str, str] | None = None,
) -> IntegrationSettings:
    values = os.environ if environ is None else environ
    return _validate_integration_settings(values)
```

`login_ready` requires only password hash and session secret, so the public login page can explain incomplete configuration. `credential_ready` additionally requires master key, valid origin-only internal/public URLs with distinct production hosts, archive directory, and a PostgreSQL `DATABASE_URL`. Parse `FACAI_INTEGRATIONS_TRUSTED_PROXY_CIDRS` with `ipaddress.ip_network(..., strict=True)` into the immutable tuple; it controls only administrator-login source resolution, not public route authorization. Existing non-integration routes never call a fail-fast loader.

- [ ] **Step 4: Implement versioned AES-GCM envelopes and key separation**

Define credential purposes `app_secret`, `access_token`, and `refresh_token`. Envelope JSON has exactly:

```json
{"v":1,"alg":"A256GCM","nonce":"AAECAwQFBgcICQoL","ciphertext":"dGVzdA","tag":"AAECAwQFBgcICQoLDA0ODw"}
```

Use a random 12-byte nonce and `purpose.value.encode()` as AAD. Split `AESGCM.encrypt()` output into ciphertext and 16-byte tag for serialization. Never accept unknown versions or algorithms.

Derive the buyer digest key with HKDF-SHA256 and `info=b"facai-integrations/buyer-id-hmac/v1"`; return `hmac.new(derived_key, external_id.encode(), sha256).hexdigest()`.

- [ ] **Step 5: Implement recursive PII and secret redaction**

Normalize keys by lowercasing and removing non-alphanumeric characters. Ban at minimum buyer/receiver names, mobile/phone, ID card, detailed address, access/refresh tokens, App Secret, authorization code, cookies and ciphertext. Preserve province/city and non-sensitive external IDs. `assert_payload_safe()` must report only the banned key path, never its value.

- [ ] **Step 6: Add an offline secret generator**

`scripts/generate_integration_secrets.py` prints a Base64url 32-byte master key, Base64url 48-byte session secret, and a scrypt password hash for a password read with `getpass`. It must never echo the password or write a file.

- [ ] **Step 7: Redact OAuth query parameters from runtime access logs**

Add a logging filter in `services/runtime_logging.py` that sanitizes `record.msg` and string elements of `record.args` for callback query keys `code`, `state`, `access_token`, `refresh_token`, `sign` and `signature` before the rotating handler formats the record. Test a synthetic `uvicorn.access` record containing sentinel query values and assert the output contains `[REDACTED]` but not the sentinels. Keep non-sensitive path/provider/request IDs visible.

- [ ] **Step 8: Run tests and scan for sentinel leakage**

Run: `python -m unittest tests.test_integration_settings tests.test_integration_crypto tests.test_integration_redaction tests.test_service_runtime -v`

Run: `rg -n "test-access-token|test-refresh-token|test-app-secret" . --glob '!tests/**' --glob '!.git/**'`

Expected: tests pass and the scan returns no production-code hits.

- [ ] **Step 9: Commit the security primitives**

Commit: `git add integrations/settings.py integrations/crypto.py integrations/redaction.py scripts/generate_integration_secrets.py config.py services/runtime_logging.py tests/test_integration_settings.py tests/test_integration_crypto.py tests/test_integration_redaction.py tests/test_service_runtime.py && git commit -m "feat: encrypt integration credentials"`

---

### Task 7: Add A Dedicated Integration Administrator Session

**Files:**
- Create: `integrations/admin_auth.py`
- Create: `integrations/audit.py`
- Create: `integrations/schemas.py`
- Create: `routers/integrations.py`
- Modify: `main.py`
- Modify: `scripts/facai_server.py`
- Test: `tests/test_integration_auth.py`
- Test: `tests/test_integration_audit.py`
- Test: `tests/test_security_hardening.py`
- Test: `tests/test_service_runtime.py`

- [ ] **Step 1: Write failing password, session, throttle and boundary tests**

Tests must cover:

- approved scrypt strings verify; wrong password and malformed strings fail without timing-sensitive early exits;
- session cookie issue/verify, signature tamper, eight-hour expiry and future `iat` rejection;
- five failures in a rolling 15-minute window cause a 15-minute persistent lock;
- two forwarded client IPs behind the same trusted proxy receive independent counters; an untrusted peer cannot spoof its source/scheme with `X-Forwarded-For` or `X-Forwarded-Proto`;
- a trusted proxy request with missing/malformed `X-Forwarded-For` or an invalid forwarded scheme returns a stable 503 configuration error before password verification;
- trusted-proxy HTTP upstream plus overwritten `X-Forwarded-Proto: https` is treated as HTTPS and emits a Secure cookie; `http` remains rejected outside loopback development;
- success resets the throttle and all outcomes create sanitized audit rows;
- `POST /api/integrations/session` is public, unknown JSON fields return 422, and no response includes the password/hash;
- `DELETE /api/integrations/session` expires only `facai_integrations_session`;
- an unprotected legacy API remains accessible while a protected integration probe returns 401;
- HTTPS cookies contain `HttpOnly`, `SameSite=Lax`, `Secure`, `Path=/`; localhost HTTP omits only `Secure`;
- non-local HTTP login is rejected.

Use a temporary integration database/session dependency override. Build ASGI scopes with explicit loopback/untrusted/trusted IP-literal `client` tuples instead of relying on TestClient's synthetic `testclient` hostname. Do not mutate module-global `database.engine` in parallel tests.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_auth tests.test_integration_audit -v`

Expected: imports/endpoints fail.

- [ ] **Step 3: Implement scrypt hashing and verification**

Use the fixed encoding:

```text
$scrypt$n=32768,r=8,p=1${salt_base64url}${digest_64_bytes_base64url}
```

Implement:

Implement `hash_admin_password(password: str, *, salt: bytes | None = None) -> str` and `verify_admin_password(password: str, encoded_hash: str) -> bool` with the exact encoding and parameters below.

Call `hashlib.scrypt(password_bytes, salt=salt, n=32768, r=8, p=1, dklen=64, maxmem=134_217_728)` and `hmac.compare_digest`. Reject passwords longer than 512 UTF-8 bytes before scrypt to bound CPU/memory work.

- [ ] **Step 4: Implement a signed, expiring stateless session**

Use compact canonical JSON with `sid`, `iat`, `exp`, version 1, Base64url without padding, and an HMAC-SHA256 signature from the session secret:

Implement `issue_admin_session(*, session_secret: bytes, now: datetime | None = None) -> str` and `verify_admin_session(cookie: str, *, session_secret: bytes, now: datetime | None = None) -> AdminSessionClaims` using the exact claims and checks below.

Generate `sid` from 32 random bytes. Verification checks structure, exact version, signature, `iat <= now + 60s`, and `now < exp <= iat + 8h`. Never log the cookie or sid; audit stores only `sha256(sid)`.

- [ ] **Step 5: Resolve a trustworthy login source and implement transactional persistent throttling**

Implement `resolve_login_request_context(request, trusted_proxy_networks) -> LoginRequestContext`. Parse the TCP peer as an IP literal. When the peer is outside all trusted networks, ignore both `X-Forwarded-For` and `X-Forwarded-Proto`, use the peer and raw ASGI scheme. When the peer is trusted, require a syntactically valid comma-separated list of IP literals, append the peer, walk right-to-left across trusted proxy hops, and select the first remaining client address (or the leftmost forwarded address when every hop is trusted). If raw ASGI scheme is `https`, effective scheme is HTTPS and no forwarded scheme is needed; if raw scheme is `http`, require exactly one overwritten `X-Forwarded-Proto` value restricted to `http|https`, and production login still requires effective `https`. Missing/malformed forwarding chain, or missing/malformed scheme on a raw-HTTP trusted hop, fails with 503; it must never collapse users to the shared proxy address or mark spoofed HTTP as secure. The production proxy must overwrite—not append arbitrary client input to—both forwarding headers.

Disable Uvicorn's automatic proxy-header rewriting in both launch paths (`proxy_headers=False`, `forwarded_allow_ips=""`) so `request.client` and the raw scheme remain trustworthy transport facts and the application performs this validation exactly once. Add a runtime regression test for both `scripts/facai_server.py` and the `main.py` direct-run path. The login endpoint's HTTPS rejection and cookie `Secure` decision use `LoginRequestContext.effective_scheme`, never `request.url.scheme` directly.

Derive `source_digest = HMAC(session_secret, b"login-source/v1:" + resolved_ip.packed)`, including the IP version through the packed length.

Insert the `IntegrationLoginThrottle` source digest with PostgreSQL `ON CONFLICT DO NOTHING`, then select the row `FOR UPDATE` inside the login transaction so concurrent first attempts cannot bypass the counter. Reset the rolling window after 15 minutes. On the fifth failure set `locked_until = now + 15 minutes`. A locked request does not run scrypt again, returns 429 with integer `retry_after_seconds`, and writes a `login_locked` audit event.

- [ ] **Step 6: Implement allowlisted audit writes**

`write_security_audit()` accepts only event-specific allowlisted detail keys. Call `assert_payload_safe()` before insert. It never stores request bodies, exception reprs, headers, IPs, credentials, codes, raw state, cookie, or session ID.

- [ ] **Step 7: Add session endpoints and the dependency**

Define strict schemas:

```python
class IntegrationLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=512)


async def require_integration_admin(
    request: Request,
    db: Session = Depends(get_db),
) -> AdminSessionClaims:
    settings = load_integration_settings()
    claims = integration_admin_session_or_none(request, settings=settings)
    if claims is None:
        raise HTTPException(status_code=401, detail="Integration administrator session required")
    return claims
```

In `routers/integrations.py`, keep a public `session_router` and an `admin_router` with `dependencies=[Depends(require_integration_admin)]`. Add `GET /api/integrations/session` as a protected probe for UI bootstrap, plus public POST and protected DELETE.

Register both routers in `main.py` without touching `routers/auth.py`.

- [ ] **Step 8: Run focused and legacy security tests**

Run: `python -m unittest tests.test_integration_auth tests.test_integration_audit tests.test_security_hardening tests.test_request_hardening -v`

Expected: all pass; legacy app/API remain no-login.

- [ ] **Step 9: Commit administrator protection**

Commit: `git add integrations/admin_auth.py integrations/audit.py integrations/schemas.py routers/integrations.py main.py scripts/facai_server.py tests/test_integration_auth.py tests/test_integration_audit.py tests/test_security_hardening.py tests/test_service_runtime.py && git commit -m "feat: protect integration administration"`

---

### Task 8: Store Platform App Configurations Without Secret Disclosure

**Files:**
- Create: `integrations/app_configs.py`
- Modify: `integrations/schemas.py`
- Modify: `routers/integrations.py`
- Test: `tests/test_integration_app_configs.py`

- [ ] **Step 1: Write failing CRUD and disclosure tests**

Test provider listing and `PUT /api/integrations/providers/{provider}/app-config` for:

- strict provider enum and `extra="forbid"` body;
- a new Secret encrypts and stores a tail mask; an omitted Secret preserves the old ciphertext; explicit `clear_secret=true` clears it;
- plaintext/ciphertext never appears in response, logs, audit or `repr`;
- missing credential readiness returns 503 with a stable `security_configuration_incomplete` code;
- unauthenticated requests return JSON 401;
- provider response separates documented, configured and live-verified capability stages.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_app_configs -v`

Expected: endpoints/services absent.

- [ ] **Step 3: Implement strict request and response schemas**

Use:

```python
class AppConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=200)
    app_secret: SecretStr | None = None
    clear_secret: bool = False


class AppConfigView(BaseModel):
    provider: Provider
    app_id: str | None
    secret_configured: bool
    secret_mask: str | None
    status: str
    updated_at: datetime | None
```

Reject a request that supplies both `app_secret` and `clear_secret=true`.

- [ ] **Step 4: Implement transactional upsert and audit**

Encrypt with purpose `app_secret`; store only ciphertext and the final four characters separately. Return `AppConfigView` built from selected safe columns, never ORM `__dict__`. Audit summary codes are `app_config_created`, `app_config_updated`, and `app_secret_cleared`.

- [ ] **Step 5: Add provider endpoints**

Add protected `GET /api/integrations/providers` and protected `PUT /api/integrations/providers/{provider}/app-config`. Readiness errors must not include the missing environment values, only their names.

- [ ] **Step 6: Run tests and commit**

Run: `python -m unittest tests.test_integration_app_configs tests.test_integration_crypto tests.test_integration_auth -v`

Commit: `git add integrations/app_configs.py integrations/schemas.py routers/integrations.py tests/test_integration_app_configs.py && git commit -m "feat: store encrypted platform app configurations"`

---

### Task 9: Enforce OAuth State And The Public Callback Host Fence

**Files:**
- Create: `integrations/connectors/__init__.py`
- Create: `integrations/connectors/base.py`
- Create: `integrations/connectors/registry.py`
- Create: `integrations/oauth.py`
- Create: `integrations/connections.py`
- Modify: `integrations/schemas.py`
- Modify: `routers/integrations.py`
- Modify: `main.py`
- Test: `tests/test_integration_oauth.py`
- Test: `tests/test_integration_public_boundary.py`

- [ ] **Step 1: Write failing OAuth and host-fence tests**

Use a fake connector registered in a test-local registry. Cover:

- state has at least 256 bits of entropy but only SHA-256 is stored;
- provider, initiating session digest for audit, ten-minute expiry and one-time use are enforced atomically;
- an absolute/external return path is rejected;
- callback succeeds without the host-only administrator cookie when valid one-time state/code arrive on the distinct public host, then 303 redirects to the exact configured internal origin plus safe relative path;
- redirect query contains only allowlisted `provider` and stable `oauth_result` codes—never code, state, Token or provider error text;
- callback exchange failure leaves the one-time state consumed, stores no credentials/connections, and records sanitized audit;
- successful callback encrypts one token bundle per authorization, then creates all discovered accounts without copying tokens to connections;
- replay, wrong provider and expired state return 400; supplying an unrelated cookie cannot change state validation;
- a request using the configured public callback host gets 404 for `/`, `/healthz`, `/app`, `/api/integrations/providers` and static paths;
- that same host can reach only GET OAuth callbacks and GET/POST event paths;
- the exact configured internal host is accepted by Host validation and can reach `/app/api-connections`, while an unrelated hostname is rejected;
- event calls return 503 until a provider-specific verified event handler is registered.

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_integration_oauth tests.test_integration_public_boundary -v`

Expected: missing connector/OAuth/boundary implementations.

- [ ] **Step 3: Establish the connector registry seam**

Put the complete approved `EcommerceConnector` protocol in `integrations/connectors/base.py`, using dataclasses from `integrations/types.py`. Registry lookup accepts only `Provider` and raises `ConnectorUnavailable` until a real implementation is registered. Add a separate optional `EventCapableConnector` protocol with `verify_event(headers, body) -> VerifiedEvent`; `VerifiedEvent` includes safe external subject/event IDs and the catalog-proven `EventIdScope` needed for multi-account routing/dedupe. Do not put HTTP event methods into the base connector.

- [ ] **Step 4: Implement state creation and atomic consumption**

Implement `create_oauth_state(db, *, provider, session_id, return_path, now=None) -> str` and `consume_oauth_state(db, *, raw_state, provider, now=None) -> IntegrationOAuthState` with the exact atomic rules below.

Generate raw state with `secrets.token_urlsafe(32)` and store SHA-256 only. Store `sha256(session_id)` for audit but never require or recover the session at callback, because the public and internal hosts deliberately use separate host-only cookies. Validate return paths with `urlsplit`: scheme/netloc/query/fragment must be empty and path must equal `/app/api-connections` or start with `/app/api-connections/`. Consume with one SQLAlchemy conditional update using predicates `consumed_at IS NULL`, `expires_at > now`, matching provider/state hash, plus `RETURNING`, so two callbacks cannot both win.

- [ ] **Step 5: Implement authorization start and callback completion**

Protected `POST /api/integrations/providers/{provider}/authorize` checks app config/readiness, creates state bound to current session, calls connector `authorization_url`, and returns only the official URL.

Public `GET /integrations/oauth/callback/{provider}` does not require or inspect the administrator cookie. It atomically consumes/commits valid state in a short transaction before any outbound request, then calls `exchange_code`; a failure requires a fresh authorization attempt and cannot replay the old state. With the token bundle only in memory, call `discover_accounts` before opening the persistence transaction. Only after both outbound calls succeed does one short transaction encrypt/upsert authorization by `(provider, external_subject_id)` and upsert all discovered connections. No outbound network call occurs while a database transaction/row lock is held. Any failure stores no partial credentials/connections and writes a separate sanitized audit transaction.

Build the completion redirect only as `validated_internal_origin + stored_safe_return_path`, adding allowlisted `provider` and stable `oauth_result=success|exchange_failed` parameters. Never derive the origin from callback `Host`, `Referer`, provider parameters or state contents. Test the complete browser sequence internal authorize → fake provider → public callback without admin cookie → internal center, and prove the same relative path on the public callback host remains fenced 404.

- [ ] **Step 6: Add the callback-host middleware**

Implement a small middleware in `main.py` before general route handling. If `Host` equals the hostname/port from `FACAI_INTEGRATIONS_PUBLIC_BASE_URL`, allow only:

```python
PUBLIC_CALLBACKS = {
    ("GET", "/integrations/oauth/callback/"),
    ("GET", "/integrations/events/"),
    ("POST", "/integrations/events/"),
}
```

Use exact prefix plus a strict provider path segment; reject suffixes and traversal. Return generic 404 for every other path. Extend the existing Host allowlist logic with the exact normalized hostname/port from both configured internal and public origins, never a wildcard. Only the exact public origin is classified as callback-fenced; the exact internal origin follows normal route handling, and all unrelated named hosts are rejected by the existing request-hardening layer. This is defense in depth; the deployment proxy must still expose only callback paths.

- [ ] **Step 7: Run tests and commit**

Run: `python -m unittest tests.test_integration_oauth tests.test_integration_public_boundary tests.test_request_hardening tests.test_security_hardening -v`

Commit: `git add integrations/connectors integrations/oauth.py integrations/connections.py integrations/schemas.py routers/integrations.py main.py tests/test_integration_oauth.py tests/test_integration_public_boundary.py && git commit -m "feat: enforce integration OAuth callback boundary"`

---

### Task 10: Foundation Verification Gate

**Files:**
- Verify only; change files only to fix failures within this plan's scope.

- [ ] **Step 1: Run all focused unit tests**

Run:

```powershell
python -m unittest tests.test_database_dialects tests.test_integration_settings tests.test_integration_models tests.test_integration_crypto tests.test_integration_redaction tests.test_integration_auth tests.test_integration_audit tests.test_integration_app_configs tests.test_integration_oauth tests.test_integration_public_boundary -v
```

Expected: all pass.

- [ ] **Step 2: Run PostgreSQL migration gates**

Run:

```powershell
if (-not $env:FACAI_TEST_DATABASE_URL) { throw 'FACAI_TEST_DATABASE_URL must reference the disposable PostgreSQL test database' }
python scripts/assert_disposable_postgres.py --env FACAI_TEST_DATABASE_URL --ack-env FACAI_DESTRUCTIVE_TEST_DATABASE_ACK
python -m unittest tests.test_alembic_postgres tests.test_sqlite_to_postgres_migration -v
```

Expected: no skips, clean downgrade/upgrade/metadata comparison, dry-run rollback and apply sequence tests all pass.

- [ ] **Step 3: Run legacy database and security regressions**

Run:

```powershell
python -m unittest tests.test_sqlite_compat_migrations tests.test_creator_migrations tests.test_security_hardening tests.test_request_hardening tests.test_service_runtime -v
```

Expected: all pass; `/healthz` still checks only the configured local database and not platforms.

- [ ] **Step 4: Run compilation and full suite**

Run:

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

Expected: zero failures. If unrelated pre-existing tests fail, record exact names and prove the same failure on the plan's starting commit before continuing.

- [ ] **Step 5: Review secret leakage and worktree scope**

Run:

```powershell
rg -n "access[_-]?token|refresh[_-]?token|app[_-]?secret|receiver|mobile|phone|id_card|detail_address" integrations integration_models.py routers/integrations.py
git status --short
git diff --check
```

Expected: matches are only field names, redaction rules, encryption code and safe masks; no real values; only intended files changed.

- [ ] **Step 6: Record the foundation checkpoint**

Create a final commit only if verification required fixes:

`git commit -m "test: verify ecommerce integration foundation"`
