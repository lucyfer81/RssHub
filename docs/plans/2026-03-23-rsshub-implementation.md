# RssHub Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建一个个人 RSS 订阅管理系统，支持 AI 评分、翻译、总结和偏好学习

**Architecture:** 单体分层架构 - FastAPI + SQLite + ChromaDB，APScheduler 处理后台任务

**Tech Stack:** FastAPI, SQLAlchemy, ChromaDB, APScheduler, Jina.ai, Jinja2

---

## Phase 1: 项目基础设施

### Task 1: 项目初始化

**Files:**
- Create: `pyproject.toml`
- Create: `.env`
- Create: `app/__init__.py`

**Step 1: 创建 pyproject.toml**

```toml
[project]
name = "rsshub"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "jinja2",
    "sqlalchemy",
    "aiosqlite",
    "httpx",
    "feedparser",
    "chromadb",
    "apscheduler",
    "pydantic-settings",
    "python-dotenv",
    "jieba",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 2: 安装依赖**

Run: `uv sync`

**Step 3: 创建 .env 配置**

```bash
# 数据库
DATABASE_URL=sqlite:///./data/rss.db
CHROMA_PERSIST_DIR=./chroma_db

# LLM API
LLM_BASE_URL=https://api.edgefn.net/v1
LLM_API_KEY=sk-CIpA52k8NwmRDNVm85567929D6Bd45659b636d09217d28Fd
LLM_MODEL=Qwen3-Next-80B-A3B-Instruct

# Embedding API
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=sk-jatkrvbkdhjmvbodgewoagmnzhrvhwycquydryyhjgfzggbj
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B

# 定时任务
SCHEDULER_ENABLED=true
SYNC_INTERVAL_HOURS=1
PREFERENCE_UPDATE_INTERVAL_HOURS=24

# RSS 抓取
MAX_ITEMS_PER_FEED=50
FETCH_TIMEOUT=30

# Jina.ai 全文抓取
JINA_RATE_LIMIT_SECONDS=2

# 分享链接
SHARE_BASE_URL=http://localhost:8000/share
```

**Step 4: 创建 app 目录结构**

Run: `mkdir -p app/routes app/services app/templates data`

**Step 5: 创建 app/__init__.py**

```python
# RssHub Application
__version__ = "0.1.0"
```

**Step 6: Commit**

```bash
git add pyproject.toml .env app/
git commit -m "chore: 项目初始化，添加依赖和配置"
```

---

### Task 2: 配置管理

**Files:**
- Create: `app/config.py`

**Step 1: 创建配置模块**

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # 数据库
    database_url: str = "sqlite:///./data/rss.db"
    chroma_persist_dir: str = "./chroma_db"

    # LLM API
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    # Embedding API
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str

    # 定时任务
    scheduler_enabled: bool = True
    sync_interval_hours: int = 1
    preference_update_interval_hours: int = 24

    # RSS 抓取
    max_items_per_feed: int = 50
    fetch_timeout: int = 30

    # Jina.ai
    jina_rate_limit_seconds: int = 2

    # 分享
    share_base_url: str

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Step 2: Commit**

```bash
git add app/config.py
git commit -m "feat: 添加配置管理模块"
```

---

### Task 3: 数据库模型

**Files:**
- Create: `app/database.py`
- Create: `app/models.py`

**Step 1: 创建数据库连接**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import get_settings

settings = get_settings()

# 转换同步 URL 为异步 URL
async_db_url = settings.database_url.replace("sqlite://", "sqlite+aiosqlite://")

engine = create_async_engine(
    async_db_url,
    echo=False,
)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

**Step 2: 创建数据模型**

```python
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
```

**Step 3: Commit**

```bash
git add app/database.py app/models.py
git commit -m "feat: 添加数据库模型"
```

---

### Task 4: Pydantic Schemas

**Files:**
- Create: `app/schemas.py`

**Step 1: 创建 Schema 模块**

```python
from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import Optional

class FeedBase(BaseModel):
    name: str
    url: str
    enabled: bool = True

class FeedCreate(FeedBase):
    pass

class FeedResponse(FeedBase):
    id: int
    last_synced_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ItemBase(BaseModel):
    title: str
    link: str
    summary: Optional[str] = None
    published_at: Optional[datetime] = None

class ItemResponse(ItemBase):
    id: int
    feed_id: int
    title_zh: Optional[str] = None
    summary_zh: Optional[str] = None
    content: Optional[str] = None
    content_zh: Optional[str] = None
    summary_ai: Optional[str] = None
    score_summary: Optional[float] = None
    score_full: Optional[float] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class ItemUpdate(BaseModel):
    status: str

class ShareResponse(BaseModel):
    id: int
    item_id: int
    share_code: str
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class PreferenceResponse(BaseModel):
    id: int
    item_id: int
    feedback: str
    keywords: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
```

**Step 2: Commit**

```bash
git add app/schemas.py
git commit -m "feat: 添加 Pydantic schemas"
```

---

## Phase 2: 核心服务层

### Task 5: RSS 抓取服务

**Files:**
- Create: `app/services/rss_fetcher.py`
- Create: `tests/test_rss_fetcher.py`

**Step 1: 写测试**

```python
import pytest
from app.services.rss_fetcher import RSSFetcher

@pytest.mark.asyncio
async def test_fetch_feed_items():
    fetcher = RSSFetcher()
    items = await fetcher.fetch("https://simonwillison.net/atom/everything/")
    assert len(items) > 0
    assert "title" in items[0]
    assert "link" in items[0]
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/test_rss_fetcher.py -v`
Expected: FAIL

**Step 3: 实现 RSS 抓取服务**

```python
import feedparser
import httpx
from hashlib import md5
from typing import List, Dict
from datetime import datetime
from app.config import get_settings

settings = get_settings()

class RSSFetcher:
    def __init__(self):
        self.timeout = settings.fetch_timeout

    async def fetch(self, url: str) -> List[Dict]:
        """抓取 RSS 源，返回文章列表"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            feed = feedparser.parse(response.content)

        items = []
        for entry in feed.entries[:settings.max_items_per_feed]:
            # 生成去重 key
            dedupe_key = md5(entry.get('link', '').encode()).hexdigest()

            items.append({
                "title": entry.get('title', ''),
                "link": entry.get('link', ''),
                "summary": entry.get('summary', ''),
                "published_at": self._parse_date(entry.get('published')),
                "dedupe_key": dedupe_key,
            })

        return items

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析日期"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        except:
            return None
```

**Step 4: 运行测试确认通过**

Run: `pytest tests/test_rss_fetcher.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/rss_fetcher.py tests/test_rss_fetcher.py
git commit -m "feat: 添加 RSS 抓取服务"
```

---

### Task 6: 全文抓取服务 (Jina.ai)

**Files:**
- Create: `app/services/content_fetcher.py`
- Create: `tests/test_content_fetcher.py`

**Step 1: 写测试**

```python
import pytest
from app.services.content_fetcher import ContentFetcher

@pytest.mark.asyncio
async def test_fetch_full_content():
    fetcher = ContentFetcher()
    content = await fetcher.fetch("https://example.com/article")
    assert len(content) > 0
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/test_content_fetcher.py -v`
Expected: FAIL

**Step 3: 实现全文抓取服务**

```python
import httpx
import asyncio
from typing import Optional
from app.config import get_settings

settings = get_settings()

class ContentFetcher:
    def __init__(self):
        self.rate_limit = settings.jina_rate_limit_seconds
        self._last_fetch = 0

    async def fetch(self, url: str) -> str:
        """使用 Jina.ai Reader API 抓取全文"""
        # 频率控制
        await self._rate_limit()

        jina_url = f"https://r.jina.ai/{url}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(jina_url)
            response.raise_for_status()
            return response.text

    async def _rate_limit(self):
        """简单的频率控制"""
        if self._last_fetch:
            elapsed = asyncio.get_event_loop().time() - self._last_fetch
            if elapsed < self.rate_limit:
                await asyncio.sleep(self.rate_limit - elapsed)
        self._last_fetch = asyncio.get_event_loop().time()
```

**Step 4: 运行测试确认通过**

Run: `pytest tests/test_content_fetcher.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/content_fetcher.py tests/test_content_fetcher.py
git commit -m "feat: 添加全文抓取服务 (Jina.ai)"
```

---

### Task 7: LLM 翻译服务

**Files:**
- Create: `app/services/translator.py`
- Create: `tests/test_translator.py`

**Step 1: 写测试**

```python
import pytest
from app.services.translator import Translator

@pytest.mark.asyncio
async def test_translate_text():
    translator = Translator()
    result = await translator.translate("Hello, world!", target_lang="中文")
    assert "你好" in result or "世界" in result
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/test_translator.py -v`
Expected: FAIL

**Step 3: 实现翻译服务**

```python
import httpx
import json
from app.config import get_settings

settings = get_settings()

class Translator:
    def __init__(self):
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def translate(self, text: str, target_lang: str = "中文") -> str:
        """翻译文本到目标语言"""
        prompt = f"请将以下文本翻译成{target_lang}，只返回翻译结果，不要解释：\n\n{text}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
```

**Step 4: 运行测试确认通过**

Run: `pytest tests/test_translator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/translator.py tests/test_translator.py
git commit -m "feat: 添加 LLM 翻译服务"
```

---

### Task 8: AI 评分服务

**Files:**
- Create: `app/services/scorer.py`
- Create: `tests/test_scorer.py`

**Step 1: 写测试**

```python
import pytest
from app.services.scorer import Scorer

@pytest.mark.asyncio
async def test_score_item():
    scorer = Scorer()
    score = await scorer.score(
        title="AI 的未来",
        summary="讨论人工智能的发展趋势",
        user_preferences="喜欢: AI, 机器学习; 不喜欢: 政治"
    )
    assert 0 <= score <= 100
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/test_scorer.py -v`
Expected: FAIL

**Step 3: 实现评分服务**

```python
import httpx
from app.config import get_settings

settings = get_settings()

class Scorer:
    def __init__(self):
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def score(self, title: str, summary: str, user_preferences: str = "") -> float:
        """基于用户偏好对文章进行评分 (0-100)"""
        prompt = f"""请根据用户偏好对文章进行评分。

用户偏好:
{user_preferences}

文章:
标题: {title}
摘要: {summary}

请给出 0-100 的评分，只返回数字，不要解释。评分标准：
- 非常符合用户兴趣: 80-100
- 比较符合: 60-79
- 一般: 40-59
- 不太符合: 20-39
- 完全不符合: 0-19
"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            result = response.json()

            score_text = result["choices"][0]["message"]["content"].strip()
            # 提取数字
            import re
            match = re.search(r'\d+', score_text)
            if match:
                score = float(match.group())
                return min(max(score, 0), 100)  # 限制在 0-100

            return 50.0  # 默认分数
```

**Step 4: 运行测试确认通过**

Run: `pytest tests/test_scorer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/scorer.py tests/test_scorer.py
git commit -m "feat: 添加 AI 评分服务"
```

---

### Task 9: AI 总结服务

**Files:**
- Create: `app/services/summarizer.py`
- Create: `tests/test_summarizer.py`

**Step 1: 写测试**

```python
import pytest
from app.services.summarizer import Summarizer

@pytest.mark.asyncio
async def test_summarize():
    summarizer = Summarizer()
    summary = await summarizer.summarize("这是一篇很长的文章内容...")
    assert len(summary) > 0
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/test_summarizer.py -v`
Expected: FAIL

**Step 3: 实现总结服务**

```python
import httpx
from app.config import get_settings

settings = get_settings()

class Summarizer:
    def __init__(self):
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def summarize(self, content: str, lang: str = "中文") -> str:
        """生成文章摘要"""
        prompt = f"""请用{lang}为以下文章写一个简洁的摘要（200字以内）：

{content[:4000]}  # 限制输入长度
"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
```

**Step 4: 运行测试确认通过**

Run: `pytest tests/test_summarizer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/summarizer.py tests/test_summarizer.py
git commit -m "feat: 添加 AI 总结服务"
```

---

### Task 10: 偏好学习服务

**Files:**
- Create: `app/services/preference.py`
- Create: `tests/test_preference.py`

**Step 1: 写测试**

```python
import pytest
from app.services.preference import PreferenceService

@pytest.mark.asyncio
async def test_extract_keywords():
    service = PreferenceService()
    keywords = await service.extract_keywords("这是一篇关于人工智能和机器学习的文章")
    assert "人工智能" in keywords or "机器学习" in keywords
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/test_preference.py -v`
Expected: FAIL

**Step 3: 实现偏好学习服务**

```python
import httpx
import jieba
import json
from app.config import get_settings

settings = get_settings()

class PreferenceService:
    def __init__(self):
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def extract_keywords(self, text: str) -> list[str]:
        """提取关键词"""
        # 使用 jieba 分词
        words = jieba.cut(text)
        # 过滤停用词和短词
        keywords = [w for w in words if len(w) >= 2]
        # 返回前 10 个高频词（简化版）
        from collections import Counter
        counter = Counter(keywords)
        return [word for word, _ in counter.most_common(10)]

    async def get_user_preferences(self, db_session) -> str:
        """聚合用户偏好为提示词"""
        # 这里简化实现，实际应该从 preferences 表聚合
        return "喜欢: AI, 技术, 编程; 不喜欢: 政治, 娱乐"

    async def learn_from_feedback(self, item_id: int, feedback: str, score_diff: float = None):
        """从用户反馈中学习"""
        # 这里简化，实际应该存储到 preferences 表
        pass
```

**Step 4: 运行测试确认通过**

Run: `pytest tests/test_preference.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/preference.py tests/test_preference.py
git commit -m "feat: 添加偏好学习服务"
```

---

### Task 11: 定时任务调度器

**Files:**
- Create: `app/services/scheduler.py`

**Step 1: 实现调度器**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.config import get_settings
from app.services.rss_fetcher import RSSFetcher
from app.services.translator import Translator
from app.services.scorer import Scorer

settings = get_settings()

class Scheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.fetcher = RSSFetcher()
        self.translator = Translator()
        self.scorer = Scorer()

    async def sync_feeds(self):
        """同步所有 RSS 源"""
        # 这里简化，实际应该从数据库获取 feeds
        print("Syncing feeds...")

    def start(self):
        if settings.scheduler_enabled:
            # RSS 同步任务
            self.scheduler.add_job(
                self.sync_feeds,
                IntervalTrigger(hours=settings.sync_interval_hours),
                id="sync_feeds",
            )
            self.scheduler.start()
            print("Scheduler started")

    def stop(self):
        self.scheduler.shutdown()
```

**Step 2: Commit**

```bash
git add app/services/scheduler.py
git commit -m "feat: 添加定时任务调度器"
```

---

## Phase 3: API 路由

### Task 12: Feeds 路由

**Files:**
- Create: `app/routes/feeds.py`
- Create: `tests/test_feeds_route.py`

**Step 1: 写测试**

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_feeds(client: AsyncClient):
    response = await client.get("/feeds")
    assert response.status_code == 200
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/test_feeds_route.py -v`
Expected: FAIL

**Step 3: 实现 Feeds 路由**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Feed
from app.schemas import FeedCreate, FeedResponse
from app.services.rss_fetcher import RSSFetcher

router = APIRouter(prefix="/feeds", tags=["feeds"])

@router.get("", response_model=list[FeedResponse])
async def get_feeds(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Feed))
    return result.scalars().all()

@router.post("", response_model=FeedResponse)
async def create_feed(feed: FeedCreate, session: AsyncSession = Depends(get_session)):
    db_feed = Feed(**feed.dict())
    session.add(db_feed)
    await session.commit()
    await session.refresh(db_feed)
    return db_feed

@router.post("/{feed_id}/sync")
async def sync_feed(feed_id: int, session: AsyncSession = Depends(get_session)):
    """手动同步某个源"""
    # 实现同步逻辑
    return {"message": "Sync started"}
```

**Step 4: 运行测试确认通过**

Run: `pytest tests/test_feeds_route.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/feeds.py tests/test_feeds_route.py
git commit -m "feat: 添加 Feeds API 路由"
```

---

### Task 13: Items 路由

**Files:**
- Create: `app/routes/items.py`

**Step 1: 实现 Items 路由**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Item
from app.schemas import ItemResponse, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])

@router.get("", response_model=list[ItemResponse])
async def get_items(
    status: str = Query("inbox"),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Item)
        .where(Item.status == status)
        .order_by(Item.score_summary.desc())
    )
    return result.scalars().all()

@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item).where(Item.id == item_id))
    return result.scalar_one()

@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    update: ItemUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one()
    item.status = update.status
    await session.commit()
    await session.refresh(item)

    # 触发后续任务
    if update.status == "reading":
        # 触发抓取全文、翻译、总结
        pass
    elif update.status == "discarded":
        # 记录偏好学习
        pass

    return item
```

**Step 2: Commit**

```bash
git add app/routes/items.py
git commit -m "feat: 添加 Items API 路由"
```

---

### Task 14: 主应用入口

**Files:**
- Create: `app/main.py`

**Step 1: 创建 FastAPI 应用**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routes import feeds, items
from app.services.scheduler import Scheduler

app = FastAPI(title="RssHub")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(feeds.router)
app.include_router(items.router)

# 模板
templates = Jinja2Templates(directory="app/templates")

# 调度器
scheduler = Scheduler()

@app.on_event("startup")
async def startup():
    await init_db()
    scheduler.start()

@app.on_event("shutdown")
async def shutdown():
    scheduler.stop()

@app.get("/")
async def root():
    return {"message": "RssHub API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Step 2: Commit**

```bash
git add app/main.py
git commit -m "feat: 添加 FastAPI 应用入口"
```

---

## Phase 4: 前端模板

### Task 15: 基础模板

**Files:**
- Create: `app/templates/base.html`

**Step 1: 创建基础模板**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}RssHub{% endblock %}</title>
    <style>
        body { font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .nav a { margin-left: 15px; text-decoration: none; color: #333; }
        .nav a:hover { text-decoration: underline; }
        .item { border-bottom: 1px solid #eee; padding: 15px 0; }
        .item-title { font-size: 18px; margin-bottom: 5px; }
        .item-meta { font-size: 14px; color: #666; }
        .score { background: #4CAF50; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .btn { padding: 5px 15px; border: none; border-radius: 4px; cursor: pointer; }
        .btn-primary { background: #2196F3; color: white; }
        .btn-secondary { background: #f5f5f5; }
    </style>
</head>
<body>
    <div class="header">
        <h1>RssHub</h1>
        <nav class="nav">
            <a href="/inbox">Inbox</a>
            <a href="/reading">Reading</a>
            <a href="/discarded">Discarded</a>
            <a href="/feeds">Feeds</a>
        </nav>
    </div>
    {% block content %}{% endblock %}
</body>
</html>
```

**Step 2: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: 添加基础模板"
```

---

### Task 16: Inbox 页面

**Files:**
- Create: `app/templates/inbox.html`

**Step 1: 创建 Inbox 页面**

```html
{% extends "base.html" %}

{% block title %}Inbox - RssHub{% endblock %}

{% block content %}
<h2>待筛选文章 ({{ items|length }})</h2>

{% for item in items %}
<div class="item">
    <div class="item-title">
        {{ item.title_zh or item.title }}
        <span class="score">{{ item.score_summary or '?' }}</span>
    </div>
    <div class="item-meta">
        {{ item.summary_zh or item.summary }}
    </div>
    <div style="margin-top: 10px;">
        <button class="btn btn-primary" onclick="moveToReading({{ item.id }})">阅读</button>
        <button class="btn btn-secondary" onclick="discard({{ item.id }})">丢弃</button>
        <a href="/items/{{ item.id }}">详情</a>
    </div>
</div>
{% endfor %}

<script>
async function moveToReading(id) {
    await fetch(`/items/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'reading' }) });
    location.reload();
}
async function discard(id) {
    await fetch(`/items/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'discarded' }) });
    location.reload();
}
</script>
{% endblock %}
```

**Step 2: 添加对应路由**

```python
# 在 app/main.py 添加
from fastapi import Request

@app.get("/inbox")
async def inbox(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Item)
        .where(Item.status == "inbox")
        .order_by(Item.score_summary.desc())
    )
    items = result.scalars().all()
    return templates.TemplateResponse("inbox.html", {"request": request, "items": items})
```

**Step 3: Commit**

```bash
git add app/templates/inbox.html
git commit -m "feat: 添加 Inbox 页面"
```

---

## Phase 5: 导出和分享功能

### Task 17: Markdown 导出

**Files:**
- Create: `app/routes/exports.py`

**Step 1: 实现导出路由**

```python
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Item

router = APIRouter(prefix="/exports", tags=["exports"])

@router.post("/items/{item_id}/markdown")
async def export_markdown(item_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one()

    markdown = f"""# {item.title_zh or item.title}

**原文链接**: {item.link}

## 摘要

{item.summary_zh or item.summary}

## AI 总结

{item.summary_ai or '暂无'}

## 全文

{item.content_zh or item.content}

---

*由 RssHub 生成*
"""

    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={item.id}.md"}
    )
```

**Step 2: Commit**

```bash
git add app/routes/exports.py
git commit -m "feat: 添加 Markdown 导出功能"
```

---

### Task 18: 分享链接

**Files:**
- Create: `app/routes/shares.py`
- Create: `app/templates/share.html`

**Step 1: 实现分享路由**

```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Item, Share
from app.schemas import ShareResponse
import secrets
from datetime import datetime, timedelta

router = APIRouter(prefix="/shares", tags=["shares"])

@router.post("/items/{item_id}", response_model=ShareResponse)
async def create_share(item_id: int, session: AsyncSession = Depends(get_session)):
    share_code = secrets.urlsafe_urlsafe(8)
    expires_at = datetime.now() + timedelta(days=30)

    share = Share(item_id=item_id, share_code=share_code, expires_at=expires_at)
    session.add(share)
    await session.commit()
    await session.refresh(share)

    return share

@router.get("/items/{item_id}")
async def get_share(item_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one()
    return {"share_url": f"/share/{item.id}"}
```

**Step 2: 创建分享模板**

```html
{% extends "base.html" %}

{% block title %}{{ item.title_zh or item.title }} - 分享{% endblock %}

{% block content %}
<article>
    <h1>{{ item.title_zh or item.title }}</h1>
    <p><strong>来源:</strong> <a href="{{ item.link }}">{{ item.link }}</a></p>

    {% if item.summary_ai %}
    <section>
        <h2>AI 总结</h2>
        <p>{{ item.summary_ai }}</p>
    </section>
    {% endif %}

    <section>
        <h2>内容</h2>
        <div>{{ item.content_zh or item.content }}</div>
    </section>
</article>

<hr>
<p><small>由 RssHub 生成并分享</small></p>
{% endblock %}
```

**Step 3: 添加公开访问路由**

```python
# 在 app/main.py 添加
@app.get("/share/{code}")
async def share_page(code: str, request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Share).join(Item).where(Share.share_code == code)
    )
    share = result.scalar_one_or_none()
    if not share:
        return {"error": "分享链接不存在或已过期"}

    item_result = await session.execute(select(Item).where(Item.id == share.item_id))
    item = item_result.scalar_one()

    return templates.TemplateResponse("share.html", {"request": request, "item": item})
```

**Step 4: Commit**

```bash
git add app/routes/shares.py app/templates/share.html
git commit -m "feat: 添加分享链接功能"
```

---

## Phase 6: 收尾

### Task 19: 初始化数据

**Files:**
- Create: `scripts/init_feeds.py`

**Step 1: 创建初始化脚本**

```python
import asyncio
from app.database import AsyncSession, get_session
from app.models import Feed

INITIAL_FEEDS = [
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"},
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
]

async def init():
    async for session in get_session():
        for feed_data in INITIAL_FEEDS:
            feed = Feed(**feed_data)
            session.add(feed)
        await session.commit()
        print(f"Added {len(INITIAL_FEEDS)} feeds")
        break

if __name__ == "__main__":
    asyncio.run(init())
```

**Step 2: Commit**

```bash
git add scripts/init_feeds.py
git commit -m "feat: 添加初始化脚本"
```

---

### Task 20: README 和文档

**Files:**
- Create: `README.md`

**Step 1: 创建 README**

```markdown
# RssHub

个人 RSS 订阅管理系统，支持 AI 评分、翻译、总结和偏好学习。

## 功能

- RSS 源管理和同步
- AI 自动评分和排序
- 中英文翻译
- 全文抓取和 AI 总结
- 偏好学习
- 分享链接
- Markdown 导出

## 安装

```bash
uv sync
```

## 配置

复制 `.env.example` 为 `.env`，填入配置。

## 运行

```bash
uv run python -m app.main
```

访问 http://localhost:8000
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: 添加 README"
```

---

## 完成检查清单

- [ ] 所有测试通过: `pytest`
- [ ] 应用正常启动: `uv run python -m app.main`
- [ ] 可以访问 Inbox 页面
- [ ] 可以添加 RSS 源
- [ ] 定时任务正常工作
- [ ] 可以导出 Markdown
- [ ] 可以生成分享链接
