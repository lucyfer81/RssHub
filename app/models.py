from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, UniqueConstraint
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
    feed_id = Column(Integer, ForeignKey("feeds.id"), nullable=False)

    # 原始内容
    title = Column(String, nullable=False)
    link = Column(String, unique=True, nullable=False)
    summary = Column(Text)
    published_at = Column(DateTime)

    # 翻译内容
    title_zh = Column(String)
    summary_zh = Column(Text)

    # 全文内容
    content = Column(Text)
    content_zh = Column(Text)
    summary_ai = Column(Text)

    # 评分
    score_summary = Column(Float)
    score_full = Column(Float)

    # 状态
    status = Column(String, default="inbox")  # inbox/reading/discarded

    # 向量
    embedding_id = Column(String)

    # 去重
    dedupe_key = Column(String, unique=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class Preference(Base):
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    feedback = Column(String, nullable=False)  # approved/discarded
    keywords = Column(Text)  # JSON
    score_diff = Column(Float)
    created_at = Column(DateTime, default=func.now())

class Share(Base):
    __tablename__ = "shares"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    share_code = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
