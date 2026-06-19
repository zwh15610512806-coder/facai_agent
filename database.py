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
        if "products" in table_names:
            columns = {column["name"] for column in inspector.get_columns("products")}
            if "pending_fields" not in columns:
                connection.execute(text("ALTER TABLE products ADD COLUMN pending_fields JSON"))

        if "ai_interface_settings" in table_names:
            columns = {column["name"] for column in inspector.get_columns("ai_interface_settings")}
            if "api_key_secret" not in columns:
                connection.execute(text("ALTER TABLE ai_interface_settings ADD COLUMN api_key_secret TEXT"))
            if "base_url_override" not in columns:
                connection.execute(text("ALTER TABLE ai_interface_settings ADD COLUMN base_url_override VARCHAR(500)"))
