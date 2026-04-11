# RSS 流水线重构 — 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 RSS 处理流程重构为单次定时流水线：抓取 → 摘要评分 → 按分数排序抓全文 → 全文评分 → 保存文章，去掉翻译和用户触发 pipeline。

**Architecture:** 单定时任务线性流水线，每天 0 点执行。阶段1 轻量（RSS + 摘要评分），阶段2 重量级（按分数排序后依次抓全文 + 全文评分 + 摘要）。文章保存为 `articles/YYYY-MM-DD/{slug}.md`。状态简化为 unread/read。

**Tech Stack:** FastAPI, SQLAlchemy (async/aiosqlite), APScheduler, httpx, Patchright, feedparser

---

### Task 1: 新建 ArticleStore 服务

**Files:**
- Create: `app/services/article_store.py`

**Step 1: 实现 ArticleStore**

```python
# app/services/article_store.py
import os
import re
import yaml
from datetime import datetime
from pathlib import Path


class ArticleStore:
    """将全文保存为 Markdown 文件"""

    def __init__(self, base_dir: str = "articles"):
        self.base_dir = Path(base_dir)

    def _slugify(self, title: str) -> str:
        """标题转 slug"""
        slug = title.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = slug.strip('-')
        return slug[:80] or 'untitled'

    def _resolve_path(self, date_str: str, slug: str) -> Path:
        """解析路径，处理冲突"""
        dir_path = self.base_dir / date_str
        dir_path.mkdir(parents=True, exist_ok=True)

        file_path = dir_path / f"{slug}.md"
        if not file_path.exists():
            return file_path

        # 同名冲突追加数字
        for i in range(2, 100):
            file_path = dir_path / f"{slug}-{i}.md"
            if not file_path.exists():
                return file_path

        return dir_path / f"{slug}-{datetime.now().timestamp()}.md"

    def save(self, item, content: str, feed_name: str = "") -> str:
        """保存文章为 Markdown 文件，返回相对路径"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        if item.published_at:
            date_str = item.published_at.strftime("%Y-%m-%d")

        slug = self._slugify(item.title)
        file_path = self._resolve_path(date_str, slug)

        frontmatter = {
            "title": item.title,
            "link": item.link,
            "published_at": date_str,
            "feed": feed_name,
            "score_summary": item.score_summary,
            "score_full": item.score_full,
            "read_time_minutes": item.read_time_minutes,
        }

        # 过滤 None 值
        frontmatter = {k: v for k, v in frontmatter.items() if v is not None}

        md_content = f"---\n{yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)}---\n\n{content}"
        file_path.write_text(md_content, encoding="utf-8")

        # 返回相对路径
        return f"{date_str}/{file_path.name}"
```

**Step 2: Commit**

```bash
git add app/services/article_store.py
git commit -m "feat: add ArticleStore service for saving articles as markdown files"
```

---

### Task 2: 改造 Scorer — 新增 score_full 方法

**Files:**
- Modify: `app/services/scorer.py`

**Step 1: 在 Scorer 类中新增 score_full 方法**

在 `scorer.py` 的 `Scorer` 类末尾添加：

```python
    async def score_full(self, title: str, content: str, user_preferences: str = "") -> float:
        """基于全文内容对文章进行评分 (0-100)"""
        if not title or not title.strip():
            raise ValueError("title 不能为空")
        if not content or not content.strip():
            raise ValueError("content 不能为空")

        preferences_text = user_preferences if user_preferences.strip() else "AI/LLM、编程开发、技术深度文章"
        truncated = content[:4000]

        prompt = f"""你是一个内容推荐评分助手。请根据用户偏好和文章内容，给出 0-100 的精准评分。

## 用户偏好
{preferences_text}

## 待评分文章
标题: {title}
正文: {truncated}

## 评分标准（必须严格执行）
1. **主题相关性 (40分)**
   - 直接涉及 AI/LLM/编程: 35-40分
   - 技术相关但非核心: 20-34分
   - 非技术内容: 0-19分

2. **内容深度 (30分)**
   - 深度技术分析/原创研究: 25-30分
   - 有见解的评论/教程: 15-24分
   - 轻资讯/转载: 5-14分
   - 纯营销/标题党: 0-4分

3. **时效性与新颖性 (20分)**
   - 最新突破/公告: 15-20分
   - 行业趋势分析: 8-14分
   - 陈旧内容: 0-7分

4. **可读性 (10分)**
   - 清晰易懂有结构: 8-10分
   - 一般可读: 4-7分
   - 晦涩难懂: 0-3分

## 输出要求
只输出一个 0-100 之间的数字（保留1位小数），不要任何其他内容。
"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()
                result = response.json()

                if "choices" not in result or not result["choices"]:
                    raise ValueError("API 响应缺少 choices 字段")

                score_text = result["choices"][0]["message"]["content"].strip()
                match = re.search(r'\b(100(?:\.0+)?|[1-9]?\d(?:\.\d+)?)\b', score_text)
                if match:
                    score = float(match.group())
                    return min(max(score, 0), 100)

                return 50.0
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise RuntimeError(f"全文评分失败: {e}") from e
```

**Step 2: Commit**

```bash
git add app/services/scorer.py
git commit -m "feat: add score_full method to Scorer for full-text scoring"
```

---

### Task 3: 改造 Model — 新增 article_path，去掉翻译字段，简化状态

**Files:**
- Modify: `app/models.py`

**Step 1: 修改 Item 模型**

在 `app/models.py` 中，将 `Item` 类改为：

```python
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
    key_points = Column(Text)  # JSON 格式
    read_time_minutes = Column(Integer)
    article_path = Column(String)  # 相对路径: YYYY-MM-DD/slug.md

    # 评分
    score_summary = Column(Float)
    score_full = Column(Float)

    # 状态: unread / read
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
```

**Step 2: 删除旧数据库以触发重建（开发环境）**

**注意：** 这会清除现有数据。因为是开发阶段，直接删除让 SQLAlchemy 重建。

```bash
rm -f data/rss.db
```

**Step 3: Commit**

```bash
git add app/models.py
git commit -m "refactor: simplify Item model - remove translation fields, add article_path, simplify status to unread/read"
```

---

### Task 4: 改造 Schemas — 匹配新的 Item 模型

**Files:**
- Modify: `app/schemas.py`

**Step 1: 更新 schemas**

```python
class ItemResponse(ItemBase):
    id: int
    feed_id: int
    content: Optional[str] = None
    summary_ai: Optional[str] = None
    key_points: Optional[str] = None
    read_time_minutes: Optional[int] = None
    article_path: Optional[str] = None
    score_summary: Optional[float] = None
    score_full: Optional[float] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class ItemUpdate(BaseModel):
    status: Literal["read", "unread"]
```

**Step 2: Commit**

```bash
git add app/schemas.py
git commit -m "refactor: update schemas to match new Item model"
```

---

### Task 5: 重写 Scheduler — 两阶段流水线

**Files:**
- Modify: `app/services/scheduler.py`

**Step 1: 重写 scheduler.py**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from sqlalchemy import select
from app.config import get_settings
from app.database import async_session
from app.models import Feed, Item
from app.services.rss_fetcher import RSSFetcher
from app.services.scorer import Scorer
from app.services.content_fetcher import ContentFetcher
from app.services.summarizer import Summarizer
from app.services.article_store import ArticleStore

settings = get_settings()


class Scheduler:
    """定时任务调度器，每天 0 点执行 RSS 同步流水线"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.fetcher = RSSFetcher()
        self.content_fetcher = ContentFetcher()
        self.scorer = Scorer()
        self.summarizer = Summarizer()
        self.article_store = ArticleStore()

    async def sync_feeds(self):
        """两阶段流水线：RSS抓取+摘要评分 → 按分数排序抓全文+全文评分"""
        print(f"[{datetime.now()}] 开始同步 RSS 源...")

        # ===== 阶段1: RSS 抓取 + 摘要评分 =====
        await self._phase1_fetch_and_score_summary()

        # ===== 阶段2: 全文抓取 + 全文评分 + 摘要生成 =====
        await self._phase2_fetch_full_and_score()

        print(f"[{datetime.now()}] 同步完成")

    async def _phase1_fetch_and_score_summary(self):
        """阶段1: 抓取 RSS 源，入库并做摘要评分"""
        print(f"[{datetime.now()}] 阶段1: RSS 抓取 + 摘要评分...")

        async with async_session() as session:
            result = await session.execute(
                select(Feed).where(Feed.enabled == True)
            )
            feeds = result.scalars().all()

            if not feeds:
                print("没有启用的 RSS 源")
                return

            for feed in feeds:
                try:
                    print(f"正在抓取: {feed.name} ({feed.url})")
                    items_data = await self.fetcher.fetch(feed.url)

                    if not items_data:
                        print(f"  - 未获取到内容")
                        continue

                    new_count = 0
                    for item_data in items_data:
                        async with async_session() as item_session:
                            # 去重
                            existing = await item_session.execute(
                                select(Item).where(Item.dedupe_key == item_data["dedupe_key"])
                            )
                            if existing.scalar_one_or_none():
                                continue

                            new_item = Item(
                                feed_id=feed.id,
                                title=item_data["title"],
                                link=item_data["link"],
                                summary=item_data["summary"],
                                published_at=item_data.get("published_at"),
                                dedupe_key=item_data["dedupe_key"],
                                status="unread",
                            )
                            item_session.add(new_item)
                            print(f"  - 新文章: {new_item.title[:50]}...")

                            # 摘要评分
                            try:
                                if item_data["title"] and item_data["summary"]:
                                    new_item.score_summary = await self.scorer.score(
                                        item_data["title"],
                                        item_data["summary"],
                                    )
                                else:
                                    new_item.score_summary = 50.0
                            except Exception as e:
                                print(f"    - 摘要评分失败: {e}")
                                new_item.score_summary = 50.0

                            await item_session.commit()
                            new_count += 1

                    feed.last_synced_at = datetime.now()
                    await session.commit()
                    print(f"  - 新增 {new_count} 篇文章")

                except Exception as e:
                    print(f"  - 同步失败: {e}")
                    continue

    async def _phase2_fetch_full_and_score(self):
        """阶段2: 按摘要评分从高到低，依次抓取全文、评分、生成摘要"""
        print(f"[{datetime.now()}] 阶段2: 全文抓取 + 全文评分...")

        async with async_session() as session:
            # 查询所有没有全文评分的文章，按摘要分数降序
            result = await session.execute(
                select(Item)
                .where(Item.score_full == None)
                .order_by(Item.score_summary.desc())
            )
            candidates = result.scalars().all()

            if not candidates:
                print("  - 没有待处理的文章")
                return

            print(f"  - 共 {len(candidates)} 篇文章待处理")

            # 获取 Feed 名称映射
            feed_result = await session.execute(select(Feed))
            feeds = {f.id: f.name for f in feed_result.scalars().all()}

            for item in candidates:
                try:
                    print(f"  处理: {item.title[:50]}... (摘要评分: {item.score_summary})")

                    # 抓取全文
                    content = await self.content_fetcher.fetch(item.link)
                    if not content:
                        print(f"    - 全文抓取失败，跳过")
                        continue

                    item.content = content

                    # 全文评分
                    try:
                        item.score_full = await self.scorer.score_full(
                            item.title, content
                        )
                        print(f"    - 全文评分: {item.score_full}")
                    except Exception as e:
                        print(f"    - 全文评分失败: {e}")
                        item.score_full = item.score_summary  # fallback

                    # AI 摘要
                    try:
                        item.summary_ai = await self.summarizer.summarize(content[:4000])
                    except Exception as e:
                        print(f"    - AI 摘要失败: {e}")

                    # 关键要点
                    try:
                        item.key_points = await self._extract_key_points(content[:4000])
                    except Exception as e:
                        print(f"    - 要点提取失败: {e}")

                    # 阅读时长
                    item.read_time_minutes = self._estimate_read_time(content)

                    # 保存到文件
                    feed_name = feeds.get(item.feed_id, "")
                    relative_path = self.article_store.save(item, content, feed_name)
                    item.article_path = relative_path
                    print(f"    - 已保存: {relative_path}")

                    await session.commit()

                except Exception as e:
                    print(f"    - 处理失败: {e}")
                    await session.rollback()
                    continue

    async def _extract_key_points(self, content: str) -> str:
        """提取关键要点，返回 JSON 字符串"""
        import httpx
        import json

        prompt = f"""请从以下文章中提取 3-5 个最关键的要点。每个要点用一句话概括。
直接返回要点列表，每行一个要点，不要编号，不要其他内容。

文章内容：
{content}
"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            result = response.json()
            text = result["choices"][0]["message"]["content"].strip()
            points = [line.strip().lstrip("-•* ") for line in text.split("\n") if line.strip()]
            return json.dumps([p for p in points if p][:5], ensure_ascii=False)

    def _estimate_read_time(self, text: str) -> int:
        """估算阅读时长（分钟）"""
        if not text:
            return 0
        import re
        if re.search(r'[\u4e00-\u9fff]', text):
            char_count = len(re.findall(r'[\u4e00-\u9fff]', text))
            return max(1, round(char_count / 400))
        else:
            word_count = len(text.split())
            return max(1, round(word_count / 250))

    def start(self):
        """启动调度器"""
        if settings.scheduler_enabled:
            self.scheduler.add_job(
                self.sync_feeds,
                CronTrigger(hour=0, minute=0),
                id="sync_feeds",
            )
            self.scheduler.start()
            print("Scheduler started - 每天 0:00 同步 RSS")
        else:
            print("Scheduler disabled")

    def stop(self):
        """停止调度器"""
        self.scheduler.shutdown()
        print("Scheduler stopped")
```

**Step 2: Commit**

```bash
git add app/services/scheduler.py
git commit -m "refactor: rewrite scheduler as two-phase pipeline - summary scoring then full-text scoring"
```

---

### Task 6: 改造 Items 路由 — 去掉 pipeline 触发

**Files:**
- Modify: `app/routes/items.py`

**Step 1: 简化 items.py**

```python
import json
import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Item, Preference
from app.schemas import ItemResponse, ItemUpdate
from app.services.preference import PreferenceService
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["items"])

pref_service = PreferenceService()


@router.get("", response_model=list[ItemResponse])
async def get_items(
    status: str = Query("unread"),
    session: AsyncSession = Depends(get_session),
):
    # 优先按 score_full 排序，无 score_full 时用 score_summary
    result = await session.execute(
        select(Item)
        .where(Item.status == status)
        .order_by(Item.score_full.desc().nullslast(), Item.score_summary.desc())
    )
    return result.scalars().all()


@router.get("/{item_id}", response_class=HTMLResponse)
async def get_item_detail(
    item_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    return templates.TemplateResponse(
        request, "item_detail.html", {"item": item}
    )


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    update: ItemUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.status = update.status
    await session.commit()
    await session.refresh(item)

    # 记录偏好（标记已读时）
    if update.status == "read":
        try:
            text = f"{item.title or ''} {item.summary or ''}"
            keywords = await pref_service.extract_keywords(text)
            preference = Preference(
                item_id=item.id,
                feedback="read",
                keywords=json.dumps(keywords, ensure_ascii=False),
                score_diff=1.0,
            )
            session.add(preference)
            await session.commit()
        except Exception as e:
            logger.error(f"Preference recording failed for item {item.id}: {e}")

    return item
```

**Step 2: Commit**

```bash
git add app/routes/items.py
git commit -m "refactor: simplify items route - remove pipeline trigger, support unread/read status"
```

---

### Task 7: 改造 main.py — 主页直接展示未读列表

**Files:**
- Modify: `app/main.py`

**Step 1: 重写 main.py 路由部分**

将 `/inbox` 改为 `/`，去掉 `/reading`：

```python
# 主页 - 展示未读文章列表
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    async for session in get_session():
        result = await session.execute(
            select(Item)
            .where(Item.status == "unread")
            .order_by(Item.score_full.desc().nullslast(), Item.score_summary.desc())
        )
        items = result.scalars().all()
        break
    return templates.TemplateResponse(request, "home.html", {"items": items, "active_nav": "home"})
```

同时删除 `/inbox` 和 `/reading` 路由。

**Step 2: Commit**

```bash
git add app/main.py
git commit -m "refactor: home page shows unread articles sorted by score"
```

---

### Task 8: 改造前端模板

**Files:**
- Modify: `app/templates/base.html` — 简化导航栏
- Create: `app/templates/home.html` — 替代 inbox.html
- Modify: `app/templates/item_detail.html` — 去掉翻译显示
- Delete: `app/templates/inbox.html`
- Delete: `app/templates/reading.html`

**Step 1: 改造 base.html 导航栏**

将导航改为：
```html
<nav class="nav">
    <a href="/" class="{% if active_nav == 'home' %}active{% endif %}">首页</a>
    <a href="/feeds" class="{% if active_nav == 'feeds' %}active{% endif %}">Feeds</a>
</nav>
```

**Step 2: 创建 home.html**

基于 inbox.html，去掉翻译显示，使用 score_full：

```html
{% extends "base.html" %}

{% block title %}未读文章 - RssHub{% endblock %}

{% block content %}
<h2>未读文章 ({{ items|length }})</h2>

{% if items %}
{% for item in items %}
<div class="item">
    <div class="item-title">
        {{ item.title }}
        {% set score = item.score_full or item.score_summary %}
        {% if score %}
        <span class="score {% if score >= 70 %}high{% elif score >= 40 %}medium{% else %}low{% endif %}">{{ score|int }}</span>
        {% endif %}
        {% if item.read_time_minutes %}
        <span class="read-time">~{{ item.read_time_minutes }}分钟</span>
        {% endif %}
    </div>
    {% if item.summary_ai %}
    <div class="item-meta expanded">
        <strong>AI 摘要：</strong>{{ item.summary_ai }}
    </div>
    {% elif item.summary %}
    <div class="item-meta" id="meta-{{ item.id }}">
        {{ item.summary[:300] | markdown | safe }}
    </div>
    <span class="item-meta-toggle" onclick="toggleMeta({{ item.id }})">展开</span>
    {% endif %}
    <div class="actions">
        <a href="/items/{{ item.id }}" class="btn btn-primary">阅读</a>
        <button class="btn btn-success" onclick="markRead({{ item.id }})">已读</button>
    </div>
</div>
{% endfor %}
{% else %}
<p>暂无文章</p>
{% endif %}

<script>
function toggleMeta(id) {
    const meta = document.getElementById('meta-' + id);
    const toggle = meta.nextElementSibling;
    if (meta.classList.contains('expanded')) {
        meta.classList.remove('expanded');
        toggle.textContent = '展开';
    } else {
        meta.classList.add('expanded');
        toggle.textContent = '收起';
    }
}

async function markRead(id) {
    const response = await fetch(`/items/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'read' })
    });
    if (response.ok) {
        location.reload();
    }
}
</script>
{% endblock %}
```

**Step 3: 改造 item_detail.html**

- 去掉所有 `title_zh`、`summary_zh`、`content_zh` 引用
- 排序使用 `score_full or score_summary`
- 状态判断改为 `unread`/`read`
- 去掉"查看英文原文"折叠
- 返回链接改为 `href="/"`

**Step 4: 删除旧模板**

```bash
rm app/templates/inbox.html app/templates/reading.html
```

**Step 5: Commit**

```bash
git add app/templates/
git commit -m "refactor: update templates - home page, remove translation display, simplify status"
```

---

### Task 9: 改造 exports 路由 — 去掉翻译引用

**Files:**
- Modify: `app/routes/exports.py`

**Step 1: 更新 export_markdown**

```python
    markdown = f"""# {item.title}

**原文链接**: {item.link}

## 摘要

{item.summary or '暂无'}

## AI 总结

{item.summary_ai or '暂无'}

## 全文

{item.content or '暂无'}

---

*由 RssHub 生成*
"""
```

**Step 2: Commit**

```bash
git add app/routes/exports.py
git commit -m "refactor: remove translation references from markdown export"
```

---

### Task 10: 删除不再需要的文件

**Files:**
- Delete: `app/services/translator.py`
- Delete: `app/services/reading_pipeline.py`
- Delete: `tests/test_translator.py`
- Delete: `tests/test_reading_pipeline.py`

**Step 1: 删除文件**

```bash
rm app/services/translator.py app/services/reading_pipeline.py tests/test_translator.py tests/test_reading_pipeline.py
```

**Step 2: Commit**

```bash
git add -A
git commit -m "refactor: remove translator and reading_pipeline services"
```

---

### Task 11: 更新测试

**Files:**
- Modify: `tests/conftest.py` — 确保 TestSession 使用新模型
- Modify: `tests/test_scorer.py` — 新增 score_full 测试
- Modify: `tests/test_items_route.py` — 适配新状态 unread/read
- Modify: `tests/test_feeds_route.py` — 如有引用翻译字段则清理
- Modify: `tests/test_e2e.py` — 适配新流程

**Step 1: 更新测试文件中的状态引用**

所有测试中的 `"inbox"` → `"unread"`，`"reading"` → `"read"`，`"discarded"` → `"read"`（按需）。

**Step 2: 新增 score_full 测试**

```python
# 在 tests/test_scorer.py 中添加
@pytest.mark.asyncio
async def test_score_full():
    scorer = Scorer()
    # mock LLM 响应返回 "85.5"
    score = await scorer.score_full("Test Title", "Test content " * 500)
    assert 0 <= score <= 100
```

**Step 3: 运行全部测试验证**

```bash
.venv/bin/pytest tests/ -v
```

**Step 4: Commit**

```bash
git add tests/
git commit -m "test: update tests for new pipeline - unread/read status, score_full"
```

---

### Task 12: 端到端验证

**Step 1: 删除旧数据库重建**

```bash
rm -f data/rss.db
```

**Step 2: 启动应用**

```bash
.venv/bin/python app/main.py
```

**Step 3: 验证主页**

浏览器访问 `http://localhost:5005/`，应显示未读文章列表页面。

**Step 4: 手动触发同步**

```bash
curl -X POST http://localhost:5005/sync
```

观察日志输出，确认两阶段流水线正常执行：
- 阶段1: RSS 抓取 + 摘要评分
- 阶段2: 全文抓取 + 全文评分 + 文件保存

**Step 5: 验证文章文件**

```bash
ls -la articles/
```

确认 `articles/YYYY-MM-DD/` 目录下生成了 `.md` 文件。

**Step 6: 验证详情页**

点击文章标题进入详情页，确认显示 AI 摘要、关键要点、全文内容。
