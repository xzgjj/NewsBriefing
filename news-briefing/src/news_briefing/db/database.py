"""数据库初始化与会话管理。

使用 SQLite + SQLAlchemy ORM，WAL 模式。
"""

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

# SQLAlchemy 基类
Base = declarative_base()

# 全局引擎和会话工厂
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """为 SQLite 连接启用 WAL 模式和外键约束。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


def init_db(db_path: Optional[str] = None) -> Engine:
    """初始化数据库引擎和表结构。

    Args:
        db_path: 数据库文件路径。默认为 ./data/news_briefing.db

    Returns:
        SQLAlchemy Engine 实例。
    """
    global _engine, _session_factory

    if db_path is None:
        db_path = str(Path("data") / "news_briefing.db")

    # 确保目录存在
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    db_url = f"sqlite:///{db_path}"

    logger.info(f"初始化数据库: {db_url}")

    _engine = create_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # 导入所有模型以确保它们注册到 Base
    from news_briefing.db import models  # noqa: F401

    # 创建所有表
    Base.metadata.create_all(_engine)

    _session_factory = sessionmaker(bind=_engine)

    logger.info("数据库初始化完成")
    return _engine


def get_session():
    """获取一个新的数据库会话。

    Returns:
        SQLAlchemy Session 实例。

    Raises:
        RuntimeError: 数据库未初始化。
    """
    if _session_factory is None:
        raise RuntimeError("数据库未初始化。请先调用 init_db()。")
    return _session_factory()


def get_engine() -> Engine:
    """获取数据库引擎。

    Raises:
        RuntimeError: 数据库未初始化。
    """
    if _engine is None:
        raise RuntimeError("数据库未初始化。请先调用 init_db()。")
    return _engine
