"""数据库连接与会话管理"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL
import os

# 确保数据目录存在
os.makedirs(os.path.dirname(DATABASE_URL.replace("sqlite:///", "")), exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
    Base.metadata.create_all(bind=engine)
    _ensure_compatible_columns()


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
        }
        for table_name, specs in column_specs.items():
            if table_name not in table_names:
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in specs.items():
                if column_name not in columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
