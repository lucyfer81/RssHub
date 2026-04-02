from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.database import Base

class Feed(Base):
    __tablename__ = "feeds"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, unique=True, nullable=False)
    enabled = Column(Boolean, default=True)
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    feed_id = Column(Integer, ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False)

    # 原始内容
    title = Column(String, nullable=False)
    link = Column(String, unique=True, nullable=False)
    summary = Column(Text)
    published_at = Column(DateTime)

    # 全文内容
    content = Column(Text)
    summary_ai = Column(Text)
    key_points = Column(Text)  # JSON 格式，AI 提取的关键要点
    read_time_minutes = Column(Integer)  # 预估阅读时长（分钟）
    article_path = Column(String)  # 相对路径，如 "2026-04-02/slug.md"

    # 评分
    score_summary = Column(Float)
    score_full = Column(Float)

    # 状态
    status = Column(String, default="unread")

    # 向量
    embedding_id = Column(String)

    # 去重
    dedupe_key = Column(String, unique=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_item_feed_status', 'feed_id', 'status'),
        Index('idx_item_published', 'published_at'),
        Index('idx_item_status_score', 'status', 'score_full'),
    )

class Preference(Base):
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    feedback = Column(String, nullable=False)  # approved/discarded
    keywords = Column(Text)  # JSON
    score_diff = Column(Float)
    created_at = Column(DateTime, default=func.now())

class Share(Base):
    __tablename__ = "shares"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    share_code = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
