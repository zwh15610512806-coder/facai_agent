"""数据库连接、SQLite 安全参数与轻量迁移管理。"""
from datetime import datetime
from pathlib import Path
import sqlite3

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL
import os

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


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表"""
    import models  # 确保模型类被注册到 Base.metadata
    if _schema_migration_required():
        _backup_sqlite_database()
    Base.metadata.create_all(bind=engine)
    _ensure_compatible_columns()


def _sqlite_database_path() -> Path | None:
    if not DATABASE_URL.startswith("sqlite:///") or DATABASE_URL.endswith(":memory:"):
        return None
    raw_path = DATABASE_URL.removeprefix("sqlite:///")
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return path.resolve()


def _schema_migration_required() -> bool:
    path = _sqlite_database_path()
    if path is None or not path.exists() or path.stat().st_size == 0:
        return False
    existing_tables = set(inspect(engine).get_table_names())
    required_tables = {"vector_sync_jobs", "job_runs"}
    return not required_tables.issubset(existing_tables)


def _backup_sqlite_database() -> Path | None:
    """Create a consistent SQLite backup immediately before schema migration."""
    source_path = _sqlite_database_path()
    if source_path is None or not source_path.exists():
        return None
    backup_dir = source_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{source_path.stem}_before_migration_{stamp}{source_path.suffix}"
    with sqlite3.connect(source_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)
    return backup_path


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
        }
        for table_name, specs in column_specs.items():
            if table_name not in table_names:
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in specs.items():
                if column_name not in columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
