"""数据库连接、SQLite 安全参数与轻量迁移管理。"""
import os
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

# 确保数据目录存在
os.makedirs(os.path.dirname(DATABASE_URL.replace("sqlite:///", "")), exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _connection_record):
    """Apply integrity and contention settings to every SQLite connection."""
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


_CREATOR_INTEGRITY_TRIGGERS = {
    "trg_creators_validate_insert": """
        CREATE TRIGGER IF NOT EXISTS trg_creators_validate_insert
        BEFORE INSERT ON creators
        WHEN NEW.stage NOT IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused')
        BEGIN SELECT RAISE(ABORT, 'invalid creator stage'); END
    """,
    "trg_creators_validate_update": """
        CREATE TRIGGER IF NOT EXISTS trg_creators_validate_update
        BEFORE UPDATE OF stage ON creators
        WHEN NEW.stage NOT IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused')
        BEGIN SELECT RAISE(ABORT, 'invalid creator stage'); END
    """,
    "trg_creator_followups_validate_insert": """
        CREATE TRIGGER IF NOT EXISTS trg_creator_followups_validate_insert
        BEFORE INSERT ON creator_followups
        WHEN NEW.method NOT IN ('douyin','wechat','phone','offline','other')
          OR (NEW.stage_after IS NOT NULL AND NEW.stage_after NOT IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused'))
        BEGIN SELECT RAISE(ABORT, 'invalid creator followup value'); END
    """,
    "trg_creator_followups_validate_update": """
        CREATE TRIGGER IF NOT EXISTS trg_creator_followups_validate_update
        BEFORE UPDATE OF method, stage_after ON creator_followups
        WHEN NEW.method NOT IN ('douyin','wechat','phone','offline','other')
          OR (NEW.stage_after IS NOT NULL AND NEW.stage_after NOT IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused'))
        BEGIN SELECT RAISE(ABORT, 'invalid creator followup value'); END
    """,
    "trg_creator_collaborations_validate_insert": """
        CREATE TRIGGER IF NOT EXISTS trg_creator_collaborations_validate_insert
        BEFORE INSERT ON creator_collaborations
        WHEN NEW.collaboration_type NOT IN ('short_video','live','graphic','other')
          OR NEW.status NOT IN ('planned','in_progress','completed','cancelled')
          OR NEW.amount_status NOT IN ('pending','confirmed')
        BEGIN SELECT RAISE(ABORT, 'invalid creator collaboration value'); END
    """,
    "trg_creator_collaborations_validate_update": """
        CREATE TRIGGER IF NOT EXISTS trg_creator_collaborations_validate_update
        BEFORE UPDATE OF collaboration_type, status, amount_status ON creator_collaborations
        WHEN NEW.collaboration_type NOT IN ('short_video','live','graphic','other')
          OR NEW.status NOT IN ('planned','in_progress','completed','cancelled')
          OR NEW.amount_status NOT IN ('pending','confirmed')
        BEGIN SELECT RAISE(ABORT, 'invalid creator collaboration value'); END
    """,
    "trg_creator_sample_orders_validate_insert": """
        CREATE TRIGGER IF NOT EXISTS trg_creator_sample_orders_validate_insert
        BEFORE INSERT ON creator_sample_orders
        WHEN NEW.status NOT IN ('pending_shipment','shipped','received','cancelled')
        BEGIN SELECT RAISE(ABORT, 'invalid creator sample order status'); END
    """,
    "trg_creator_sample_orders_validate_update": """
        CREATE TRIGGER IF NOT EXISTS trg_creator_sample_orders_validate_update
        BEFORE UPDATE OF status ON creator_sample_orders
        WHEN NEW.status NOT IN ('pending_shipment','shipped','received','cancelled')
        BEGIN SELECT RAISE(ABORT, 'invalid creator sample order status'); END
    """,
}


def _normalize_trigger_sql(value: str | None) -> str:
    normalized = re.sub(r"\s+", "", value or "").lower()
    return normalized.replace("ifnotexists", "").rstrip(";")


def _creator_integrity_triggers_valid(trigger_sql: dict[str, str | None]) -> bool:
    return all(
        _normalize_trigger_sql(trigger_sql.get(name)) == _normalize_trigger_sql(expected)
        for name, expected in _CREATOR_INTEGRITY_TRIGGERS.items()
    )


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Bring the database to the versioned Alembic head and initialize settings."""
    import creator_models  # noqa: F401 - 注册达人商务域模型
    import models  # noqa: F401 - 确保模型类被注册到 Base.metadata
    _run_schema_migrations()
    from services.ai_config import ensure_interface_settings
    with SessionLocal() as session:
        ensure_interface_settings(session)


def _alembic_config():
    from alembic.config import Config

    root = Path(__file__).resolve().parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    return config


def _run_schema_migrations() -> None:
    """Upgrade to Alembic head, restoring the pre-upgrade SQLite backup on failure."""
    from alembic import command
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    config = _alembic_config()
    expected_head = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
    if current_revision == expected_head:
        if _schema_migration_required():
            raise RuntimeError(
                "Database schema drift detected at the current Alembic revision; "
                "run an explicit repair migration before startup."
            )
        return

    database_path = _sqlite_database_path()
    existed_before = bool(database_path and database_path.exists() and database_path.stat().st_size)
    backup_path = _backup_sqlite_database() if existed_before else None
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        if _schema_migration_required():
            raise RuntimeError(
                "Database schema drift detected after Alembic upgrade; restore the last "
                "verified backup and run the explicit schema repair migration."
            )
    except Exception:
        engine.dispose()
        if backup_path is not None and database_path is not None:
            shutil.copy2(backup_path, database_path)
        elif not existed_before and database_path is not None:
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(f"{database_path}{suffix}")
                if candidate.exists():
                    candidate.unlink()
        raise


def _sqlite_database_path() -> Path | None:
    if engine.dialect.name != "sqlite":
        return None
    raw_path = engine.url.database
    if not raw_path or raw_path == ":memory:":
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _creator_import_committed_index_valid(inspector) -> bool:
    for index in inspector.get_indexes("creator_import_batches"):
        if index.get("name") != "uq_creator_import_committed_file":
            continue
        if not bool(index.get("unique")):
            return False
        if list(index.get("column_names") or []) != ["kind", "file_sha256"]:
            return False
        where = (index.get("dialect_options") or {}).get("sqlite_where")
        where_text = str(where) if where is not None else ""
        normalized_where = "".join(where_text.lower().split()).replace('"', "").replace("`", "")
        return normalized_where in {"status='committed'", "status=(\'committed\')"}
    return False


def _schema_migration_required() -> bool:
    path = _sqlite_database_path()
    if path is None or not path.exists() or path.stat().st_size == 0:
        return False
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = {
        "vector_sync_jobs",
        "job_runs",
        "product_rag_feedbacks",
        "vector_index_versions",
        "bd_members",
        "creators",
        "creator_portraits",
        "creator_addresses",
        "creator_followups",
        "creator_collaborations",
        "creator_collaboration_products",
        "creator_sample_orders",
        "creator_sample_order_items",
        "creator_import_batches",
    }
    if not required_tables.issubset(existing_tables):
        return True
    sample_order_columns = {column["name"] for column in inspector.get_columns("creator_sample_orders")}
    if "request_fingerprint" not in sample_order_columns:
        return True
    if "generated_scripts" in existing_tables:
        generated_script_columns = {
            column["name"] for column in inspector.get_columns("generated_scripts")
        }
        if not {
            "source_script_id",
            "source_script_source",
            "source_script_title",
            "source_script_content",
        }.issubset(generated_script_columns):
            return True
    if not _creator_import_committed_index_valid(inspector):
        return True
    with engine.connect() as connection:
        trigger_sql = {
            name: sql
            for name, sql in connection.execute(
                text("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'")
            )
        }
    return not _creator_integrity_triggers_valid(trigger_sql)


def _backup_sqlite_database() -> Path | None:
    """Create a consistent SQLite backup immediately before schema migration."""
    source_path = _sqlite_database_path()
    if source_path is None or not source_path.exists():
        return None
    backup_dir = source_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{source_path.stem}_before_migration_{stamp}{source_path.suffix}"
    with closing(sqlite3.connect(source_path)) as source, closing(sqlite3.connect(backup_path)) as destination:
        source.backup(destination)
    return backup_path


def _ensure_creator_indexes():
    """Repair creator import duplicates and add indexes skipped by create_all on old tables."""
    inspector = inspect(engine)
    if "creator_import_batches" not in set(inspector.get_table_names()):
        return
    existing = {item["name"] for item in inspector.get_indexes("creator_import_batches")}
    committed_index_valid = _creator_import_committed_index_valid(inspector)
    if "uq_creator_import_committed_file" in existing and not committed_index_valid:
        with engine.begin() as connection:
            connection.execute(text('DROP INDEX "uq_creator_import_committed_file"'))
        existing.remove("uq_creator_import_committed_file")
    if "uq_creator_import_committed_file" not in existing:
        with engine.begin() as connection:
            duplicates = connection.execute(text(
                "SELECT kind, file_sha256, MIN(id) AS keep_id "
                "FROM creator_import_batches WHERE status = 'committed' "
                "GROUP BY kind, file_sha256 HAVING COUNT(*) > 1"
            )).mappings().all()
            for duplicate in duplicates:
                connection.execute(
                    text(
                        "UPDATE creator_import_batches SET status = 'duplicate' "
                        "WHERE status = 'committed' AND kind = :kind AND file_sha256 = :sha "
                        "AND id <> :keep_id"
                    ),
                    {
                        "kind": duplicate["kind"],
                        "sha": duplicate["file_sha256"],
                        "keep_id": duplicate["keep_id"],
                    },
                )
    from creator_models import CreatorImportBatch

    for index in CreatorImportBatch.__table__.indexes:
        if index.name in {
            "ix_creator_import_batch_file_lookup",
            "uq_creator_import_committed_file",
        }:
            index.create(bind=engine, checkfirst=True)


def _ensure_creator_integrity_triggers():
    """Enforce creator-domain enums for legacy SQLite tables without rebuilding them."""
    if engine.dialect.name != "sqlite":
        return
    table_names = set(inspect(engine).get_table_names())
    required_tables = {
        "creators",
        "creator_followups",
        "creator_collaborations",
        "creator_sample_orders",
    }
    if not required_tables.issubset(table_names):
        return
    with engine.begin() as connection:
        existing = {
            name: sql
            for name, sql in connection.execute(
                text("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'")
            )
        }
        for name, ddl in _CREATOR_INTEGRITY_TRIGGERS.items():
            if _normalize_trigger_sql(existing.get(name)) != _normalize_trigger_sql(ddl):
                connection.execute(text(f'DROP TRIGGER IF EXISTS "{name}"'))
                connection.execute(text(ddl))


def _ensure_compatible_columns():
    """Add lightweight SQLite columns that create_all will not add to old tables."""
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        column_specs = {
            "products": {
                "pending_fields": "JSON",
            },
            "viral_scripts": {
                "is_high_conversion": "INTEGER DEFAULT 0",
            },
            "generated_scripts": {
                "ai_model": "VARCHAR(100)",
                "is_high_conversion": "INTEGER DEFAULT 0",
                "source_script_id": "INTEGER",
                "source_script_source": "VARCHAR(20)",
                "source_script_title": "VARCHAR(300)",
                "source_script_content": "TEXT",
            },
            "reference_scripts": {
                "is_high_conversion": "INTEGER DEFAULT 0",
                "embedding_id": "VARCHAR(200)",
            },
            "ai_interface_settings": {
                "provider": "VARCHAR(50) NOT NULL DEFAULT 'deepseek'",
                "model": "VARCHAR(120) NOT NULL DEFAULT 'deepseek-chat'",
                "max_tokens": "INTEGER NOT NULL DEFAULT 2400",
                "api_key_secret": "TEXT",
                "base_url_override": "VARCHAR(500)",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            },
            "ai_usage_records": {
                "actor_name": "VARCHAR(100)",
            },
            "product_rag_query_logs": {
                "pipeline_version": "VARCHAR(50) NOT NULL DEFAULT 'product-rag-v3-facets'",
                "index_version": "VARCHAR(100) NOT NULL DEFAULT 'legacy'",
                "query_plan": "JSON",
                "candidate_trace": "JSON",
                "selected_evidence": "JSON",
                "rerank_status": "VARCHAR(30) NOT NULL DEFAULT 'skipped'",
                "answer_mode": "VARCHAR(30) NOT NULL DEFAULT 'fallback'",
            },
            "qianchuan_import_batches": {
                "row_count": "INTEGER DEFAULT 0",
                "imported_count": "INTEGER DEFAULT 0",
                "skipped_count": "INTEGER DEFAULT 0",
                "amount_field": "VARCHAR(100)",
                "created_at": "DATETIME",
            },
            "qianchuan_material_performance": {
                "material_evaluation": "VARCHAR(200)",
                "material_duration": "VARCHAR(50)",
                "material_created_time": "VARCHAR(50)",
                "material_source": "VARCHAR(100)",
                "tags": "VARCHAR(500)",
                "amount_field": "VARCHAR(100)",
                "transaction_amount": "FLOAT DEFAULT 0.0",
                "order_count": "INTEGER DEFAULT 0",
                "user_pay_amount": "FLOAT DEFAULT 0.0",
                "roi": "FLOAT DEFAULT 0.0",
                "impressions": "INTEGER DEFAULT 0",
                "ctr": "FLOAT DEFAULT 0.0",
                "spend": "FLOAT DEFAULT 0.0",
                "clicks": "INTEGER DEFAULT 0",
                "cvr": "FLOAT DEFAULT 0.0",
                "play_3s_rate": "FLOAT DEFAULT 0.0",
                "play_10s_rate": "FLOAT DEFAULT 0.0",
                "avg_watch_seconds": "FLOAT DEFAULT 0.0",
                "completion_rate": "FLOAT DEFAULT 0.0",
                "plan_count": "INTEGER DEFAULT 0",
                "product_count": "INTEGER DEFAULT 0",
                "raw_data": "JSON",
                "created_at": "DATETIME",
            },
            "qianchuan_script_bindings": {
                "created_at": "DATETIME",
            },
            "creator_sample_orders": {
                "request_fingerprint": "VARCHAR(64)",
            },
        }
        for table_name, specs in column_specs.items():
            if table_name not in table_names:
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in specs.items():
                if column_name not in columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
