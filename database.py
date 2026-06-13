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
    if "products" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("products")}
    with engine.begin() as connection:
        if "pending_fields" not in columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN pending_fields JSON"))
