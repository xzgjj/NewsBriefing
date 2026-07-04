"""SQLAlchemy ORM 模型定义。

对应 SPEC.md §6.1 中定义的数据库表结构。
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from news_briefing.db.database import Base


class NewsItemModel(Base):
    """新闻条目表 — news_items。"""
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url_hash = Column(String(32), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    url = Column(String(2048), nullable=False)
    source_name = Column(String(200), nullable=False)
    source_tier = Column(Integer, nullable=False, default=2)
    content_snippet = Column(Text)
    published_at = Column(DateTime)
    fetched_at = Column(DateTime, default=datetime.now)
    simhash = Column(Integer, default=0)
    category = Column(String(50), default="general")
    importance = Column(String(20), default="green")
    ai_summary = Column(Text)
    detoxed_title = Column(String(500))
    certainty = Column(String(30), default="confirmed")
    cross_validated_by = Column(Text)  # JSON array as string
    score = Column(Float, default=0.0)
    briefing_id = Column(Integer, ForeignKey("briefings.id"))
    created_at = Column(DateTime, default=datetime.now)

    briefing = relationship("BriefingModel", back_populates="news_items")


class BriefingModel(Base):
    """简报表 — briefings。"""
    __tablename__ = "briefings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    mode = Column(String(20), nullable=False)
    date = Column(Date, nullable=False, index=True)
    status = Column(String(20), default="draft")
    degradation_level = Column(Integer, default=0)
    total_raw = Column(Integer, default=0)
    total_after_dedup = Column(Integer, default=0)
    total_selected = Column(Integer, default=0)
    markdown_text = Column(Text)
    feishu_card_json = Column(Text)
    delivery_status = Column(String(50))
    delivery_channel = Column(String(50))
    delivery_at = Column(DateTime)
    tavily_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    news_items = relationship("NewsItemModel", back_populates="briefing")


class WatchlistModel(Base):
    """关注列表表 — watchlist。"""
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    ticker = Column(String(50))
    market = Column(String(10))
    keywords = Column(Text, nullable=False)  # JSON array as string
    priority = Column(Integer, default=5)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class FeedbackModel(Base):
    """用户反馈表 — feedback。"""
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    briefing_id = Column(Integer, ForeignKey("briefings.id"))
    news_id = Column(Integer, ForeignKey("news_items.id"))
    action = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class SourceHealthModel(Base):
    """信源健康状态表 — source_health。"""
    __tablename__ = "source_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(200), unique=True, nullable=False)
    tier = Column(Integer, nullable=False)
    consecutive_failures = Column(Integer, default=0)
    last_success = Column(DateTime)
    last_failure = Column(DateTime)
    enabled = Column(Boolean, default=True)
    total_fetches = Column(Integer, default=0)
    total_failures = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.now)
