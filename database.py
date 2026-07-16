"""数据库连接、SQLite 安全参数与轻量迁移管理。"""
import os
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from alembic.config import Config
from sqlalchemy import MetaData, create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.schema import CreateTable

from config import DATABASE_URL


def _configure_sqlite_connection(dbapi_connection, _connection_record):
    """Apply integrity and contention settings to every SQLite connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


def create_database_engine(url: str):
    parsed_url = make_url(url)
    is_sqlite = parsed_url.get_backend_name() == "sqlite"
    options: dict[str, object] = {
        "hide_parameters": True,
        "pool_pre_ping": True,
    }
    if is_sqlite:
        options["connect_args"] = {"check_same_thread": False}
    bind = create_engine(url, **options)
    if is_sqlite:
        event.listen(bind, "connect", _configure_sqlite_connection)
    return bind


def _ensure_sqlite_parent(url: str) -> None:
    parsed_url = make_url(url)
    if parsed_url.get_backend_name() != "sqlite":
        return
    raw_path = parsed_url.database
    if not raw_path or raw_path == ":memory:":
        return
    Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent(DATABASE_URL)
engine = create_database_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
alembic_config = Config(str(Path(__file__).with_name("alembic.ini")))


def core_sqlite_metadata() -> MetaData:
    """Return application metadata without PostgreSQL-only integration tables."""
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name.startswith(("integration_", "commerce_")):
            continue
        table.to_metadata(metadata)
    return metadata


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

_ITEM_PROJECT_EXPRESSION = (
    "(SELECT generation.project_id FROM canvas_generation_items AS item "
    "JOIN canvas_generations AS generation ON generation.id = item.generation_id "
    "WHERE item.id = NEW.item_id)"
)
_GENERATION_ITEM_INTEGRITY_WHEN = """
    NOT EXISTS (
        SELECT 1 FROM image_model_profiles AS model
        WHERE model.id = NEW.model_profile_id AND model.provider_id = NEW.provider_id
    )
    OR (NEW.latest_background_asset_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM canvas_assets AS asset
        JOIN canvas_generations AS generation ON generation.id = NEW.generation_id
        WHERE asset.id = NEW.latest_background_asset_id
          AND asset.project_id = generation.project_id
    ))
    OR (NEW.latest_composed_asset_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM canvas_assets AS asset
        JOIN canvas_generations AS generation ON generation.id = NEW.generation_id
        WHERE asset.id = NEW.latest_composed_asset_id
          AND asset.project_id = generation.project_id
    ))
"""
_NEW_ITEM_GENERATION_PROJECT_EXPRESSION = (
    "(SELECT generation.project_id FROM canvas_generations AS generation "
    "WHERE generation.id = NEW.generation_id)"
)
_GENERATION_ITEM_CHILDREN_INTEGRITY_WHEN = f"""
    EXISTS (
        SELECT 1 FROM canvas_generation_item_inputs AS input
        LEFT JOIN canvas_assets AS asset ON asset.id = input.asset_id
        WHERE input.item_id = NEW.id
          AND (asset.id IS NULL
            OR asset.project_id <> {_NEW_ITEM_GENERATION_PROJECT_EXPRESSION})
    )
    OR EXISTS (
        SELECT 1 FROM canvas_generation_attempts AS attempt
        LEFT JOIN canvas_assets AS background ON background.id = attempt.background_asset_id
        LEFT JOIN canvas_assets AS background_preview
          ON background_preview.id = attempt.background_preview_asset_id
        LEFT JOIN canvas_assets AS composed ON composed.id = attempt.composed_asset_id
        LEFT JOIN canvas_assets AS composed_preview
          ON composed_preview.id = attempt.composed_preview_asset_id
        LEFT JOIN canvas_asset_operations AS operation
          ON operation.id = attempt.compose_operation_id
        WHERE attempt.item_id = NEW.id
          AND (
            (attempt.background_asset_id IS NOT NULL
              AND (background.id IS NULL
                OR background.project_id <> {_NEW_ITEM_GENERATION_PROJECT_EXPRESSION}))
            OR (attempt.background_preview_asset_id IS NOT NULL
              AND (background_preview.id IS NULL
                OR background_preview.project_id
                  <> {_NEW_ITEM_GENERATION_PROJECT_EXPRESSION}))
            OR (attempt.composed_asset_id IS NOT NULL
              AND (composed.id IS NULL
                OR composed.project_id <> {_NEW_ITEM_GENERATION_PROJECT_EXPRESSION}))
            OR (attempt.composed_preview_asset_id IS NOT NULL
              AND (composed_preview.id IS NULL
                OR composed_preview.project_id
                  <> {_NEW_ITEM_GENERATION_PROJECT_EXPRESSION}))
            OR (attempt.compose_operation_id IS NOT NULL
              AND (operation.id IS NULL
                OR operation.project_id <> {_NEW_ITEM_GENERATION_PROJECT_EXPRESSION}))
          )
    )
"""
_GENERATION_ITEM_UPDATE_INTEGRITY_WHEN = (
    f"({_GENERATION_ITEM_INTEGRITY_WHEN}) "
    f"OR ({_GENERATION_ITEM_CHILDREN_INTEGRITY_WHEN})"
)
_GENERATION_INPUT_INTEGRITY_WHEN = f"""
    NOT EXISTS (
        SELECT 1 FROM canvas_assets AS asset
        WHERE asset.id = NEW.asset_id
          AND asset.project_id = {_ITEM_PROJECT_EXPRESSION}
    )
"""
_GENERATION_ATTEMPT_INTEGRITY_WHEN = f"""
    NOT EXISTS (
        SELECT 1 FROM image_model_profiles AS model
        WHERE model.id = NEW.model_profile_id AND model.provider_id = NEW.provider_id
    )
    OR (NEW.background_asset_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM canvas_assets AS asset
        WHERE asset.id = NEW.background_asset_id
          AND asset.project_id = {_ITEM_PROJECT_EXPRESSION}
    ))
    OR (NEW.background_preview_asset_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM canvas_assets AS asset
        WHERE asset.id = NEW.background_preview_asset_id
          AND asset.project_id = {_ITEM_PROJECT_EXPRESSION}
    ))
    OR (NEW.composed_asset_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM canvas_assets AS asset
        WHERE asset.id = NEW.composed_asset_id
          AND asset.project_id = {_ITEM_PROJECT_EXPRESSION}
    ))
    OR (NEW.composed_preview_asset_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM canvas_assets AS asset
        WHERE asset.id = NEW.composed_preview_asset_id
          AND asset.project_id = {_ITEM_PROJECT_EXPRESSION}
    ))
    OR (NEW.compose_operation_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM canvas_asset_operations AS operation
        WHERE operation.id = NEW.compose_operation_id
          AND operation.project_id = {_ITEM_PROJECT_EXPRESSION}
    ))
"""
_MODEL_PROFILE_PROVIDER_INTEGRITY_WHEN = """
    EXISTS (
        SELECT 1 FROM canvas_generation_items AS item
        WHERE item.model_profile_id = NEW.id AND item.provider_id <> NEW.provider_id
    )
    OR EXISTS (
        SELECT 1 FROM canvas_generation_attempts AS attempt
        WHERE attempt.model_profile_id = NEW.id AND attempt.provider_id <> NEW.provider_id
    )
"""
_GENERATION_PROJECT_INTEGRITY_WHEN = """
    EXISTS (
        SELECT 1 FROM canvas_generation_items AS item
        LEFT JOIN canvas_assets AS background
          ON background.id = item.latest_background_asset_id
        LEFT JOIN canvas_assets AS composed
          ON composed.id = item.latest_composed_asset_id
        WHERE item.generation_id = NEW.id
          AND (
            (item.latest_background_asset_id IS NOT NULL
              AND (background.id IS NULL OR background.project_id <> NEW.project_id))
            OR (item.latest_composed_asset_id IS NOT NULL
              AND (composed.id IS NULL OR composed.project_id <> NEW.project_id))
          )
    )
    OR EXISTS (
        SELECT 1 FROM canvas_generation_item_inputs AS input
        JOIN canvas_generation_items AS item ON item.id = input.item_id
        LEFT JOIN canvas_assets AS asset ON asset.id = input.asset_id
        WHERE item.generation_id = NEW.id
          AND (asset.id IS NULL OR asset.project_id <> NEW.project_id)
    )
    OR EXISTS (
        SELECT 1 FROM canvas_generation_attempts AS attempt
        JOIN canvas_generation_items AS item ON item.id = attempt.item_id
        LEFT JOIN canvas_assets AS background ON background.id = attempt.background_asset_id
        LEFT JOIN canvas_assets AS background_preview
          ON background_preview.id = attempt.background_preview_asset_id
        LEFT JOIN canvas_assets AS composed ON composed.id = attempt.composed_asset_id
        LEFT JOIN canvas_assets AS composed_preview
          ON composed_preview.id = attempt.composed_preview_asset_id
        LEFT JOIN canvas_asset_operations AS operation
          ON operation.id = attempt.compose_operation_id
        WHERE item.generation_id = NEW.id
          AND (
            (attempt.background_asset_id IS NOT NULL
              AND (background.id IS NULL OR background.project_id <> NEW.project_id))
            OR (attempt.background_preview_asset_id IS NOT NULL
              AND (background_preview.id IS NULL
                OR background_preview.project_id <> NEW.project_id))
            OR (attempt.composed_asset_id IS NOT NULL
              AND (composed.id IS NULL OR composed.project_id <> NEW.project_id))
            OR (attempt.composed_preview_asset_id IS NOT NULL
              AND (composed_preview.id IS NULL
                OR composed_preview.project_id <> NEW.project_id))
            OR (attempt.compose_operation_id IS NOT NULL
              AND (operation.id IS NULL OR operation.project_id <> NEW.project_id))
          )
    )
"""
_ASSET_PROJECT_INTEGRITY_WHEN = """
    EXISTS (
        SELECT 1 FROM canvas_generation_items AS item
        JOIN canvas_generations AS generation ON generation.id = item.generation_id
        WHERE (item.latest_background_asset_id = NEW.id
          OR item.latest_composed_asset_id = NEW.id)
          AND generation.project_id <> NEW.project_id
    )
    OR EXISTS (
        SELECT 1 FROM canvas_generation_item_inputs AS input
        JOIN canvas_generation_items AS item ON item.id = input.item_id
        JOIN canvas_generations AS generation ON generation.id = item.generation_id
        WHERE input.asset_id = NEW.id
          AND generation.project_id <> NEW.project_id
    )
    OR EXISTS (
        SELECT 1 FROM canvas_generation_attempts AS attempt
        JOIN canvas_generation_items AS item ON item.id = attempt.item_id
        JOIN canvas_generations AS generation ON generation.id = item.generation_id
        WHERE (
          attempt.background_asset_id = NEW.id
          OR attempt.background_preview_asset_id = NEW.id
          OR attempt.composed_asset_id = NEW.id
          OR attempt.composed_preview_asset_id = NEW.id
        )
          AND generation.project_id <> NEW.project_id
    )
"""
_OPERATION_PROJECT_INTEGRITY_WHEN = """
    EXISTS (
        SELECT 1 FROM canvas_generation_attempts AS attempt
        JOIN canvas_generation_items AS item ON item.id = attempt.item_id
        JOIN canvas_generations AS generation ON generation.id = item.generation_id
        WHERE attempt.compose_operation_id = NEW.id
          AND generation.project_id <> NEW.project_id
    )
"""


def _canvas_integrity_trigger_ddl(
    *, name: str, table_name: str, action: str, when_sql: str, message: str
) -> str:
    return (
        f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {action} ON {table_name} "
        f"WHEN {when_sql} BEGIN SELECT RAISE(ABORT, '{message}'); END"
    )


_CANVAS_GENERATION_INTEGRITY_TRIGGERS = {
    "trg_canvas_generation_generations_integrity_update": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_generations_integrity_update",
        table_name="canvas_generations",
        action="UPDATE OF project_id",
        when_sql=_GENERATION_PROJECT_INTEGRITY_WHEN,
        message="invalid canvas generation project relation",
    ),
    "trg_canvas_generation_assets_integrity_update": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_assets_integrity_update",
        table_name="canvas_assets",
        action="UPDATE OF project_id",
        when_sql=_ASSET_PROJECT_INTEGRITY_WHEN,
        message="invalid canvas generation asset project relation",
    ),
    "trg_canvas_generation_operations_integrity_update": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_operations_integrity_update",
        table_name="canvas_asset_operations",
        action="UPDATE OF project_id",
        when_sql=_OPERATION_PROJECT_INTEGRITY_WHEN,
        message="invalid canvas generation operation project relation",
    ),
    "trg_canvas_generation_model_profiles_integrity_update": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_model_profiles_integrity_update",
        table_name="image_model_profiles",
        action="UPDATE OF provider_id",
        when_sql=_MODEL_PROFILE_PROVIDER_INTEGRITY_WHEN,
        message="invalid canvas generation model provider relation",
    ),
    "trg_canvas_generation_items_integrity_insert": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_items_integrity_insert",
        table_name="canvas_generation_items",
        action="INSERT",
        when_sql=_GENERATION_ITEM_INTEGRITY_WHEN,
        message="invalid canvas generation item relation",
    ),
    "trg_canvas_generation_items_integrity_update": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_items_integrity_update",
        table_name="canvas_generation_items",
        action=(
            "UPDATE OF generation_id, provider_id, model_profile_id, "
            "latest_background_asset_id, latest_composed_asset_id"
        ),
        when_sql=_GENERATION_ITEM_UPDATE_INTEGRITY_WHEN,
        message="invalid canvas generation item relation",
    ),
    "trg_canvas_generation_inputs_integrity_insert": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_inputs_integrity_insert",
        table_name="canvas_generation_item_inputs",
        action="INSERT",
        when_sql=_GENERATION_INPUT_INTEGRITY_WHEN,
        message="invalid canvas generation input relation",
    ),
    "trg_canvas_generation_inputs_integrity_update": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_inputs_integrity_update",
        table_name="canvas_generation_item_inputs",
        action="UPDATE OF item_id, asset_id",
        when_sql=_GENERATION_INPUT_INTEGRITY_WHEN,
        message="invalid canvas generation input relation",
    ),
    "trg_canvas_generation_attempts_integrity_insert": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_attempts_integrity_insert",
        table_name="canvas_generation_attempts",
        action="INSERT",
        when_sql=_GENERATION_ATTEMPT_INTEGRITY_WHEN,
        message="invalid canvas generation attempt relation",
    ),
    "trg_canvas_generation_attempts_integrity_update": _canvas_integrity_trigger_ddl(
        name="trg_canvas_generation_attempts_integrity_update",
        table_name="canvas_generation_attempts",
        action=(
            "UPDATE OF item_id, provider_id, model_profile_id, background_asset_id, "
            "background_preview_asset_id, composed_asset_id, composed_preview_asset_id, "
            "compose_operation_id"
        ),
        when_sql=_GENERATION_ATTEMPT_INTEGRITY_WHEN,
        message="invalid canvas generation attempt relation",
    ),
}

_INTEGRATION_CONNECTION_PROVIDER_UNIQUE = (
    "uq_integration_connections_id_provider"
)


def _normalize_trigger_sql(value: str | None) -> str:
    normalized = re.sub(r"\s+", "", value or "").lower()
    return normalized.replace("ifnotexists", "").rstrip(";")


def _creator_integrity_triggers_valid(trigger_sql: dict[str, str | None]) -> bool:
    return all(
        _normalize_trigger_sql(trigger_sql.get(name)) == _normalize_trigger_sql(expected)
        for name, expected in _CREATOR_INTEGRITY_TRIGGERS.items()
    )


def _canvas_generation_integrity_triggers_valid(
    trigger_sql: dict[str, str | None],
) -> bool:
    return all(
        _normalize_trigger_sql(trigger_sql.get(name))
        == _normalize_trigger_sql(expected)
        for name, expected in _CANVAS_GENERATION_INTEGRITY_TRIGGERS.items()
    )


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def assert_schema_current(bind) -> None:
    """Fail startup unless the database revision matches the Alembic head."""
    from alembic.script import ScriptDirectory

    remediation = "Run `alembic upgrade head` before starting the application."
    try:
        expected_head = ScriptDirectory.from_config(alembic_config).get_current_head()
        with bind.connect() as connection:
            current_head = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    except Exception as exc:
        raise RuntimeError(f"Unable to verify the database schema revision. {remediation}") from exc

    if not expected_head or current_head != expected_head:
        raise RuntimeError(
            "Database schema revision "
            f"{current_head or '<none>'} does not match Alembic head "
            f"{expected_head or '<none>'}. {remediation}"
        )


def init_db():
    """Bring the active database to its supported schema and initialize settings."""
    import canvas_models  # Register Product Canvas persistence models.
    import models  # 确保模型类被注册到 Base.metadata
    import creator_models  # 注册达人商务域模型
    import integration_models  # 注册电商集成控制域模型
    import commerce_models  # 预留电商业务域模型注册

    if engine.dialect.name != "sqlite":
        assert_schema_current(engine)
        return

    migration_backup = _run_schema_migrations(
        drift_check=lambda: _schema_migration_required(
            include_integration=False,
            include_canvas=False,
        )
    )
    _upgrade_canvas_generation_layout_hash_width()
    # Alembic creates the Canvas tables for a fresh database. Install the
    # idempotent guards before evaluating drift so trigger-only setup does not
    # create a misleading "pre-migration" backup for a brand-new database.
    _ensure_canvas_generation_integrity_triggers()
    if _schema_migration_required() and migration_backup is None:
        _backup_sqlite_database()
    _ensure_integration_connection_provider_unique()
    Base.metadata.create_all(bind=engine)
    _ensure_creator_indexes()
    _ensure_compatible_columns()
    _ensure_creator_integrity_triggers()
    _ensure_canvas_generation_integrity_triggers()

    from services.ai_config import ensure_interface_settings

    # Keep initialization bound to the active engine so migration tests and
    # maintenance tools can safely supply an isolated SQLite database.
    with SessionLocal(bind=engine) as session:
        ensure_interface_settings(session)


def _alembic_config():
    from alembic.config import Config

    root = Path(__file__).resolve().parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    return config


def _run_schema_migrations(*, drift_check=None) -> Path | None:
    """Upgrade to Alembic head, restoring the pre-upgrade SQLite backup on failure."""
    from alembic import command
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    if drift_check is None:
        drift_check = _schema_migration_required

    database_path = _sqlite_database_path()
    existed_before = bool(
        database_path and database_path.exists() and database_path.stat().st_size
    )
    config = _alembic_config()
    expected_head = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
    if current_revision == expected_head:
        if drift_check():
            raise RuntimeError(
                "Database schema drift detected at the current Alembic revision; "
                "run an explicit repair migration before startup."
            )
        return None

    backup_path = _backup_sqlite_database() if existed_before else None
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        if drift_check():
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
    return backup_path


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


def _integration_connection_provider_unique_valid(inspector) -> bool:
    """Return whether SQLite has the exact parent key required by commerce FKs."""
    table_names = set(inspector.get_table_names())
    if "integration_connections" not in table_names:
        return False
    expected_columns = ["id", "provider"]
    for constraint in inspector.get_unique_constraints("integration_connections"):
        if list(constraint.get("column_names") or []) == expected_columns:
            return True
    for index in inspector.get_indexes("integration_connections"):
        sqlite_where = (index.get("dialect_options") or {}).get("sqlite_where")
        if (
            bool(index.get("unique"))
            and sqlite_where is None
            and list(index.get("column_names") or []) == expected_columns
        ):
            return True
    return False


def _schema_migration_required(
    *, include_integration: bool = True, include_canvas: bool = True
) -> bool:
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
    if include_canvas:
        canvas_tables = {
            "canvas_projects",
            "canvas_project_skus",
            "canvas_assets",
            "canvas_asset_operations",
            "canvas_events",
            "image_provider_connections",
            "image_model_profiles",
            "canvas_generations",
            "canvas_generation_items",
            "canvas_generation_item_inputs",
            "canvas_generation_attempts",
        }
        if not canvas_tables.issubset(existing_tables):
            return True
    if include_integration and (
        "integration_connections" in existing_tables
        and not _integration_connection_provider_unique_valid(inspector)
    ):
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
    return not (
        _creator_integrity_triggers_valid(trigger_sql)
        and (
            not include_canvas
            or _canvas_generation_integrity_triggers_valid(trigger_sql)
        )
    )


def _ensure_integration_connection_provider_unique() -> None:
    """Repair the composite parent key before SQLite creates commerce children."""
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "integration_connections" not in table_names:
        return
    if _integration_connection_provider_unique_valid(inspector):
        return

    existing_names = {
        item.get("name")
        for item in inspector.get_indexes("integration_connections")
    }
    if _INTEGRATION_CONNECTION_PROVIDER_UNIQUE in existing_names:
        raise RuntimeError(
            "SQLite index uq_integration_connections_id_provider exists with "
            "an incompatible definition; repair it before starting the application."
        )
    with engine.begin() as connection:
        connection.execute(
            text(
                'CREATE UNIQUE INDEX "uq_integration_connections_id_provider" '
                'ON "integration_connections" ("id", "provider")'
            )
        )


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


def _drop_canvas_generation_integrity_triggers(connection) -> None:
    for trigger_name in _CANVAS_GENERATION_INTEGRITY_TRIGGERS:
        connection.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{trigger_name}"')


def _upgrade_canvas_generation_layout_hash_width() -> None:
    """Rebuild the generation-item table when only the legacy hash width exists."""

    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "canvas_generation_items" not in inspector.get_table_names():
        return
    columns = {
        column["name"]: column
        for column in inspector.get_columns("canvas_generation_items")
    }
    layout_column = columns.get("layout_hash")
    if layout_column is None:
        return
    reflected_type = str(layout_column["type"]).upper()
    if reflected_type == "VARCHAR(71)" or reflected_type != "VARCHAR(64)":
        return

    import canvas_models

    table = canvas_models.CanvasGenerationItem.__table__
    temporary = "canvas_generation_items__layout_hash_rebuild"
    create_sql = str(CreateTable(table).compile(engine)).strip()
    create_sql = create_sql.replace(
        "CREATE TABLE canvas_generation_items",
        f'CREATE TABLE "{temporary}"',
        1,
    )
    column_names = [column.name for column in table.columns]
    quoted_columns = ", ".join(f'"{name}"' for name in column_names)

    with engine.connect() as connection:
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            _drop_canvas_generation_integrity_triggers(connection)
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{temporary}"')
            connection.exec_driver_sql(create_sql)
            connection.exec_driver_sql(
                f'INSERT INTO "{temporary}" ({quoted_columns}) '
                f'SELECT {quoted_columns} FROM "canvas_generation_items"'
            )
            connection.exec_driver_sql('DROP TABLE "canvas_generation_items"')
            connection.exec_driver_sql(
                f'ALTER TABLE "{temporary}" RENAME TO "canvas_generation_items"'
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            try:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{temporary}"')
                connection.commit()
            except Exception:
                connection.rollback()
            raise RuntimeError(
                "Canvas generation layout-hash migration failed"
            ) from exc
        finally:
            if connection.in_transaction():
                connection.rollback()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
                raise RuntimeError(
                    "Canvas generation migration failed to restore foreign_keys"
                )


def _ensure_canvas_generation_integrity_triggers() -> None:
    """Install raw-write-safe ownership and provider/model integrity guards."""

    if engine.dialect.name != "sqlite":
        return
    required_tables = {
        "canvas_assets",
        "canvas_asset_operations",
        "image_model_profiles",
        "canvas_generations",
        "canvas_generation_items",
        "canvas_generation_item_inputs",
        "canvas_generation_attempts",
    }
    if not required_tables.issubset(set(inspect(engine).get_table_names())):
        return
    with engine.begin() as connection:
        existing = {
            name: sql
            for name, sql in connection.execute(
                text(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='trigger' AND name LIKE "
                    "'trg_canvas_generation_%_integrity_%'"
                )
            )
        }
        for name, ddl in _CANVAS_GENERATION_INTEGRITY_TRIGGERS.items():
            if _normalize_trigger_sql(existing.get(name)) != _normalize_trigger_sql(ddl):
                connection.execute(text(f'DROP TRIGGER IF EXISTS "{name}"'))
                connection.execute(text(ddl))


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
