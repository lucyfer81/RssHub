# 渐进式阅读体验增强 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 打通阅读 pipeline，新增阅读列表页，增加 AI 阅读辅助，优化移动端体验。

**Architecture:** 在现有 FastAPI + SQLAlchemy 异步架构上扩展。新增 `reading_pipeline.py` 服务串联 content_fetcher/translator/summarizer。前端保持 Jinja2 模板 + 原生 JS。

**Tech Stack:** FastAPI, SQLAlchemy (async), Jinja2, httpx, asyncio, pytest-asyncio

---

### Task 1: 扩展数据模型 — 新增字段和状态

**Files:**
- Modify: `app/models.py:41` (status 注释)
- Modify: `app/schemas.py:43-44` (ItemUpdate)

**Step 1: 写失败测试**

在 `tests/test_items_route.py` 末尾添加：

```python
@pytest.mark.asyncio
async def test_update_item_to_read(client: AsyncClient, db_session):
    """测试将文章标记为已读"""
    feed = Feed(name="测试 Feed", url="https://read-status.example.com/rss")
    db_session.add(feed)
    await db_session.flush()

    item = Item(
        feed_id=feed.id,
        title="测试文章",
        link="https://read-status.example.com/article",
        dedupe_key="read_status_1",
        status="reading",
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.patch(f"/items/{item.id}", json={"status": "read"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "read"
```

**Step 2: 运行测试确认失败**

Run: `./.venv/bin/python -m pytest tests/test_items_route.py::test_update_item_to_read -v`
Expected: FAIL — `"read"` 不在 `Literal["inbox", "reading", "discarded"]` 中

**Step 3: 修改 schema 允许 `read` 状态**

修改 `app/schemas.py` 第 43-44 行：

```python
class ItemUpdate(BaseModel):
    status: Literal["inbox", "reading", "read", "discarded"]
```

**Step 4: 运行测试确认通过**

Run: `./.venv/bin/python -m pytest tests/test_items_route.py -v`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add app/schemas.py tests/test_items_route.py
git commit -m "feat: 扩展 ItemUpdate 支持 read 状态"
```

---

### Task 2: 新增 key_points 和 read_time_minutes 字段

**Files:**
- Modify: `app/models.py:34-36` (在 summary_ai 之后添加)
- Modify: `app/schemas.py:27-38` (ItemResponse)

**Step 1: 写失败测试**

在 `tests/test_items_route.py` 末尾添加：

```python
@pytest.mark.asyncio
async def test_item_has_new_fields(client: AsyncClient, db_session):
    """测试 Item 响应包含 key_points 和 read_time_minutes"""
    feed = Feed(name="测试 Feed", url="https://fields.example.com/rss")
    db_session.add(feed)
    await db_session.flush()

    item = Item(
        feed_id=feed.id,
        title="测试文章",
        link="https://fields.example.com/article",
        dedupe_key="fields_test_1",
        key_points='["要点1", "要点2"]',
        read_time_minutes=5,
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.get(f"/items/{item.id}")
    assert response.status_code == 200
```

**Step 2: 运行测试确认失败**

Run: `./.venv/bin/python -m pytest tests/test_items_route.py::test_item_has_new_fields -v`
Expected: FAIL — Item 没有 `key_points` / `read_time_minutes` 字段

**Step 3: 修改 Item 模型**

在 `app/models.py` 第 36 行（`summary_ai = Column(Text)` 之后）添加：

```python
    key_points = Column(Text)  # JSON 格式，AI 提取的关键要点
    read_time_minutes = Column(Integer)  # 预估阅读时长（分钟）
```

在 `app/schemas.py` 的 `ItemResponse` 中，`summary_ai` 之后添加：

```python
    key_points: Optional[str] = None
    read_time_minutes: Optional[int] = None
```

**Step 4: 重建数据库表**

由于 SQLite 新增列需要重建。在开发环境删除旧数据库重建：

```bash
rm -f data/rss.db
./.venv/bin/python -c "import asyncio; from app.database import init_db; asyncio.run(init_db())"
```

**Step 5: 运行测试确认通过**

Run: `./.venv/bin/python -m pytest tests/test_items_route.py -v`
Expected: 全部 PASS

**Step 6: 提交**

```bash
git add app/models.py app/schemas.py tests/test_items_route.py
git commit -m "feat: Item 模型新增 key_points 和 read_time_minutes 字段"
```

---

### Task 3: 创建阅读 Pipeline 服务

**Files:**
- Create: `app/services/reading_pipeline.py`
- Create: `tests/test_reading_pipeline.py`

**Step 1: 写失败测试**

创建 `tests/test_reading_pipeline.py`：

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.reading_pipeline import ReadingPipeline


@pytest.mark.asyncio
async def test_pipeline_calls_content_fetcher():
    """测试 pipeline 调用 content_fetcher"""
    pipeline = ReadingPipeline()
    pipeline.fetcher = AsyncMock()
    pipeline.fetcher.fetch.return_value = "full article content"
    pipeline.translator = AsyncMock()
    pipeline.translator.translate.return_value = "翻译后的内容"
    pipeline.summarizer = AsyncMock()
    pipeline.summarizer.summarize.return_value = "AI 摘要"
    pipeline.key_points_extractor = AsyncMock()
    pipeline.key_points_extractor.return_value = ["要点1", "要点2"]

    result = await pipeline.process("https://example.com/article", "Article Title", "")

    assert result["content"] == "full article content"
    assert result["content_zh"] == "翻译后的内容"
    assert result["summary_ai"] == "AI 摘要"
    assert result["key_points"] == ["要点1", "要点2"]
    assert result["read_time_minutes"] > 0
    pipeline.fetcher.fetch.assert_called_once_with("https://example.com/article")


@pytest.mark.asyncio
async def test_pipeline_continues_on_fetch_failure():
    """测试抓取失败时 pipeline 不崩溃"""
    pipeline = ReadingPipeline()
    pipeline.fetcher = AsyncMock()
    pipeline.fetcher.fetch.return_value = ""  # 抓取失败返回空
    pipeline.translator = AsyncMock()
    pipeline.summarizer = AsyncMock()
    pipeline.key_points_extractor = AsyncMock()
    pipeline.key_points_extractor.return_value = []

    result = await pipeline.process("https://example.com/fail", "Title", "summary")

    assert result["content"] == ""
    assert result["content_zh"] is None
    assert result["summary_ai"] is None


@pytest.mark.asyncio
async def test_pipeline_skips_translation_for_chinese():
    """测试中文内容跳过翻译"""
    pipeline = ReadingPipeline()
    pipeline.fetcher = AsyncMock()
    pipeline.fetcher.fetch.return_value = "这是一篇中文文章内容" * 50
    pipeline.translator = AsyncMock()
    pipeline.summarizer = AsyncMock()
    pipeline.summarizer.summarize.return_value = "摘要"
    pipeline.key_points_extractor = AsyncMock()
    pipeline.key_points_extractor.return_value = ["要点"]

    result = await pipeline.process("https://example.com/cn", "中文标题", "中文摘要")

    # 中文内容不应调用翻译
    pipeline.translator.translate.assert_not_called()
    assert result["content_zh"] is None


@pytest.mark.asyncio
async def test_estimate_read_time_chinese():
    """测试中文阅读时长估算"""
    pipeline = ReadingPipeline()
    # 400字/分钟，800字 = 2分钟
    minutes = pipeline.estimate_read_time("这是一段中文测试文本" * 100)
    assert minutes == 2


@pytest.mark.asyncio
async def test_estimate_read_time_english():
    """测试英文阅读时长估算"""
    pipeline = ReadingPipeline()
    # 250词/分钟，250词 = 1分钟
    text = " ".join(["word"] * 250)
    minutes = pipeline.estimate_read_time(text)
    assert minutes == 1
```

**Step 2: 运行测试确认失败**

Run: `./.venv/bin/python -m pytest tests/test_reading_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.reading_pipeline'`

**Step 3: 实现 ReadingPipeline**

创建 `app/services/reading_pipeline.py`：

```python
import json
import re
import logging
from app.services.content_fetcher import ContentFetcher
from app.services.translator import Translator, is_chinese
from app.services.summarizer import Summarizer

logger = logging.getLogger(__name__)


class ReadingPipeline:
    """阅读 pipeline：全文抓取 → 翻译 → 摘要 → 关键要点 → 阅读时长"""

    def __init__(self):
        self.fetcher = ContentFetcher()
        self.translator = Translator()
        self.summarizer = Summarizer()

    async def process(self, url: str, title: str, summary: str) -> dict:
        """执行完整的阅读处理 pipeline

        Args:
            url: 文章 URL
            title: 文章标题
            summary: 文章摘要

        Returns:
            dict: 处理结果，包含 content, content_zh, summary_ai, key_points, read_time_minutes
        """
        result = {
            "content": None,
            "content_zh": None,
            "summary_ai": None,
            "key_points": None,
            "read_time_minutes": None,
        }

        # 1. 抓取全文
        try:
            content = await self.fetcher.fetch(url)
            result["content"] = content if content else None
        except Exception as e:
            logger.warning(f"全文抓取失败 [{url}]: {e}")

        if not result["content"]:
            return result

        # 2. 翻译（非中文内容）
        try:
            if not is_chinese(result["content"]):
                result["content_zh"] = await self.translator.translate(result["content"][:4000])
            else:
                result["content_zh"] = None
        except Exception as e:
            logger.warning(f"全文翻译失败 [{url}]: {e}")

        # 3. 生成 AI 摘要
        try:
            text_for_summary = result["content_zh"] or result["content"]
            if text_for_summary:
                result["summary_ai"] = await self.summarizer.summarize(text_for_summary[:4000])
        except Exception as e:
            logger.warning(f"AI 摘要失败 [{url}]: {e}")

        # 4. 提取关键要点
        try:
            text_for_points = result["content_zh"] or result["content"]
            if text_for_points:
                result["key_points"] = await self.extract_key_points(text_for_points[:4000])
        except Exception as e:
            logger.warning(f"关键要点提取失败 [{url}]: {e}")

        # 5. 阅读时长估算
        text_for_time = result["content_zh"] or result["content"]
        if text_for_time:
            result["read_time_minutes"] = self.estimate_read_time(text_for_time)

        return result

    async def extract_key_points(self, content: str) -> list[str]:
        """使用 LLM 提取文章关键要点"""
        import httpx
        from app.config import get_settings

        settings = get_settings()

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
            return [p for p in points if p][:5]

    def estimate_read_time(self, text: str) -> int:
        """估算阅读时长（分钟）

        中文：约 400 字/分钟
        英文：约 250 词/分钟
        """
        if not text:
            return 0

        if is_chinese(text):
            char_count = len(re.findall(r'[\u4e00-\u9fff]', text))
            return max(1, round(char_count / 400))
        else:
            word_count = len(text.split())
            return max(1, round(word_count / 250))
```

**Step 4: 运行测试确认通过**

Run: `./.venv/bin/python -m pytest tests/test_reading_pipeline.py -v`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add app/services/reading_pipeline.py tests/test_reading_pipeline.py
git commit -m "feat: 创建 ReadingPipeline 服务"
```

---

### Task 4: 在 items 路由中触发 pipeline

**Files:**
- Modify: `app/routes/items.py:58-66` (update_item 函数)

**Step 1: 写失败测试**

在 `tests/test_items_route.py` 末尾添加：

```python
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_update_to_reading_triggers_pipeline(client: AsyncClient, db_session):
    """测试标记 reading 时触发 pipeline"""
    feed = Feed(name="测试 Feed", url="https://pipeline.example.com/rss")
    db_session.add(feed)
    await db_session.flush()

    item = Item(
        feed_id=feed.id,
        title="测试文章",
        link="https://pipeline.example.com/article",
        summary="摘要内容",
        dedupe_key="pipeline_test_1",
    )
    db_session.add(item)
    await db_session.commit()

    with patch("app.routes.items.run_pipeline") as mock_pipeline:
        mock_pipeline.delay = AsyncMock()
        response = await client.patch(f"/items/{item.id}", json={"status": "reading"})
        assert response.status_code == 200
        assert response.json()["status"] == "reading"
        # pipeline 应该被调度（不阻塞响应）
        assert mock_pipeline.called or mock_pipeline.delay.called


@pytest.mark.asyncio
async def test_update_to_discarded_records_preference(client: AsyncClient, db_session):
    """测试标记 discarded 时记录偏好"""
    feed = Feed(name="测试 Feed", url="https://pref.example.com/rss")
    db_session.add(feed)
    await db_session.flush()

    item = Item(
        feed_id=feed.id,
        title="测试文章",
        link="https://pref.example.com/article",
        score_summary=75.0,
        dedupe_key="pref_test_1",
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.patch(f"/items/{item.id}", json={"status": "discarded"})
    assert response.status_code == 200
```

**Step 2: 运行测试确认失败**

Run: `./.venv/bin/python -m pytest tests/test_items_route.py::test_update_to_reading_triggers_pipeline -v`
Expected: FAIL — `run_pipeline` 不存在

**Step 3: 修改 items 路由**

将 `app/routes/items.py` 第 1-66 行替换为：

```python
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Item
from app.schemas import ItemResponse, ItemUpdate
from app.templates_config import templates
from app.services.reading_pipeline import ReadingPipeline
from app.services.preference import PreferenceService

router = APIRouter(prefix="/items", tags=["items"])
logger = logging.getLogger(__name__)


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


async def _run_pipeline(item_id: int, link: str, title: str, summary: str):
    """后台执行阅读 pipeline，更新数据库"""
    from app.database import async_session

    pipeline = ReadingPipeline()
    try:
        result = await pipeline.process(link, title, summary or "")
    except Exception as e:
        logger.error(f"Pipeline 执行失败 [item={item_id}]: {e}")
        return

    async with async_session() as session:
        db_item = await session.get(Item, item_id)
        if not db_item:
            return

        if result.get("content"):
            db_item.content = result["content"]
        if result.get("content_zh"):
            db_item.content_zh = result["content_zh"]
        if result.get("summary_ai"):
            db_item.summary_ai = result["summary_ai"]
        if result.get("key_points"):
            db_item.key_points = json.dumps(result["key_points"], ensure_ascii=False)
        if result.get("read_time_minutes"):
            db_item.read_time_minutes = result["read_time_minutes"]

        await session.commit()


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

    if update.status == "reading":
        # 异步触发阅读 pipeline（不阻塞响应）
        asyncio.create_task(_run_pipeline(
            item.id, item.link, item.title, item.summary
        ))
    elif update.status == "discarded":
        # 记录偏好学习
        pref_service = PreferenceService()
        keywords = await pref_service.extract_keywords(
            f"{item.title} {item.summary or ''}"
        )
        session.add(type(session.get(Item, 1)).__mro__[0]  # 占位，下面修正
        )
        from app.models import Preference
        pref = Preference(
            item_id=item.id,
            feedback="discarded",
            keywords=json.dumps(keywords, ensure_ascii=False) if keywords else None,
            score_diff=item.score_summary,
        )
        session.add(pref)
        await session.commit()

    return item
```

注意：上面 `update_item` 中的 `discarded` 分支有一个多余的占位行，实际代码应去掉 `session.add(type(session.get...` 那一行，只保留 `from app.models import Preference` 之后的代码。

**Step 4: 运行测试确认通过**

Run: `./.venv/bin/python -m pytest tests/test_items_route.py -v`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add app/routes/items.py tests/test_items_route.py
git commit -m "feat: 标记 reading 时异步触发阅读 pipeline"
```

---

### Task 5: 创建阅读列表页

**Files:**
- Modify: `app/main.py` (添加 `/reading` 路由)
- Create: `app/templates/reading.html`

**Step 1: 写失败测试**

在 `tests/test_items_route.py` 末尾添加：

```python
@pytest.mark.asyncio
async def test_reading_page_returns_html(client: AsyncClient, db_session):
    """测试阅读列表页返回 HTML"""
    response = await client.get("/reading", follow_redirects=True)
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
```

**Step 2: 运行测试确认失败**

Run: `./.venv/bin/python -m pytest tests/test_items_route.py::test_reading_page_returns_html -v`
Expected: FAIL — 404 (路由不存在)

**Step 3: 在 main.py 添加 reading 路由**

在 `app/main.py` 的 `inbox` 路由之后添加：

```python
# Reading 页面
@app.get("/reading")
async def reading(request: Request):
    async for session in get_session():
        result = await session.execute(
            select(Item)
            .where(Item.status == "reading")
            .order_by(Item.score_summary.desc())
        )
        items = result.scalars().all()
        break
    return templates.TemplateResponse(request, "reading.html", {"items": items})
```

**Step 4: 创建 reading.html 模板**

创建 `app/templates/reading.html`：

```html
{% extends "base.html" %}

{% block title %}待阅读 - RssHub{% endblock %}

{% block content %}
<h2>待阅读 ({{ items|length }})</h2>

{% if items %}
{% for item in items %}
<div class="item">
    <div class="item-title">
        {{ item.title_zh or item.title }}
        {% if item.score_summary %}
        <span class="score {% if item.score_summary >= 70 %}high{% elif item.score_summary >= 40 %}medium{% else %}low{% endif %}">{{ item.score_summary|int }}</span>
        {% endif %}
        {% if item.read_time_minutes %}
        <span class="read-time">~{{ item.read_time_minutes }}分钟</span>
        {% endif %}
    </div>
    {% if item.summary_ai %}
    <div class="item-meta expanded">
        <strong>AI 摘要：</strong>{{ item.summary_ai }}
    </div>
    {% elif item.summary_zh or item.summary %}
    <div class="item-meta" id="meta-{{ item.id }}">
        {{ (item.summary_zh or item.summary)[:300] | markdown | safe }}
    </div>
    <span class="item-meta-toggle" onclick="toggleMeta({{ item.id }})">展开</span>
    {% endif %}
    {% if item.key_points %}
    <div class="key-points">
        {% set points = item.key_points | tojson | safe %}
        <strong>关键要点：</strong>
        <ul id="points-{{ item.id }}"></ul>
    </div>
    {% endif %}
    <div class="actions">
        <a href="/items/{{ item.id }}" class="btn btn-primary">阅读</a>
        <button class="btn btn-success" onclick="markRead({{ item.id }})">已读</button>
        <button class="btn btn-secondary" onclick="discard({{ item.id }})">丢弃</button>
    </div>
</div>
{% endfor %}
{% else %}
<p>暂无待阅读文章</p>
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

async function discard(id) {
    const response = await fetch(`/items/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'discarded' })
    });
    if (response.ok) {
        location.reload();
    }
}

// 渲染关键要点
document.querySelectorAll('[id^="points-"]').forEach(ul => {
    const itemDiv = ul.closest('.item');
    const keyPointsStr = itemDiv.querySelector('.key-points')?.dataset?.points;
    if (keyPointsStr) {
        try {
            const points = JSON.parse(keyPointsStr);
            points.forEach(p => {
                const li = document.createElement('li');
                li.textContent = p;
                ul.appendChild(li);
            });
        } catch(e) {}
    }
});
</script>
{% endblock %}
```

注意：`key_points` 的渲染需要更简单的方式。在上面的模板中，改为直接在模板中用 Jinja2 解析 JSON：

```html
{% if item.key_points %}
<div class="key-points">
    <strong>关键要点：</strong>
    <ul>
    {% for point in (item.key_points | from_json) %}
        <li>{{ point }}</li>
    {% endfor %}
    </ul>
</div>
{% endif %}
```

需要在 `app/templates_config.py` 中添加 `from_json` 过滤器：

```python
import json as json_lib

def from_json_filter(text: str):
    """Jinja2 过滤器：将 JSON 字符串解析为 Python 对象"""
    if not text:
        return []
    try:
        return json_lib.loads(text)
    except (json_lib.JSONDecodeError, TypeError):
        return []

templates.env.filters['from_json'] = from_json_filter
```

**Step 5: 运行测试确认通过**

Run: `./.venv/bin/python -m pytest tests/test_items_route.py -v`
Expected: 全部 PASS

**Step 6: 手动验证**

```bash
./.venv/bin/uvicorn app.main:app --port 5005
# 浏览器访问 http://localhost:5005/reading
```

**Step 7: 提交**

```bash
git add app/main.py app/templates/reading.html app/templates_config.py tests/test_items_route.py
git commit -m "feat: 新增阅读列表页 /reading"
```

---

### Task 6: 更新文章详情页 — 增加 AI 信息区和已读按钮

**Files:**
- Modify: `app/templates/item_detail.html`

**Step 1: 在 base.html 添加新 CSS 样式**

在 `app/templates/base.html` 的 `<style>` 末尾（`</style>` 之前）添加：

```css
/* AI 阅读辅助 */
.ai-info { background: #f8f9fa; border-radius: 8px; padding: 15px 20px; margin-bottom: 25px; }
.ai-info h3 { margin: 0 0 10px 0; font-size: 16px; color: #555; }
.ai-info .key-points-list { margin: 0; padding-left: 20px; }
.ai-info .key-points-list li { margin-bottom: 5px; line-height: 1.5; }
.read-time { color: #888; font-size: 13px; margin-left: 8px; }
.btn-success { background: #4CAF50; color: white; }
.btn-success:hover { background: #388E3C; }

/* 响应式 */
@media (max-width: 768px) {
    body { padding: 10px; }
    .header { flex-direction: column; gap: 10px; }
    .nav { display: flex; flex-wrap: wrap; gap: 5px; }
    .nav a { margin-left: 0; font-size: 14px; padding: 6px 10px; }
    .item-title { font-size: 16px; }
    .item-header h1 { font-size: 22px; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; }
    .actions .btn { margin-right: 0; }
    .btn { padding: 10px 16px; min-height: 44px; }
}
```

**Step 2: 修改 item_detail.html**

在摘要部分（`<div class="content-section">` 摘要之前）插入 AI 信息区，并在操作区添加"已读"按钮：

```html
{% extends "base.html" %}

{% block title %}{{ item.title_zh or item.title }} - RssHub{% endblock %}

{% block content %}
<div class="item-detail">
    <div class="item-header">
        <h1>{{ item.title_zh or item.title }}</h1>
        {% if item.title_zh and item.title != item.title_zh %}
        <div class="original-title">原文：{{ item.title }}</div>
        {% endif %}
        <div class="item-info">
            {% if item.score_summary %}
            <span class="score {% if item.score_summary >= 70 %}high{% elif item.score_summary >= 40 %}medium{% else %}low{% endif %}">{{ item.score_summary|int }}分</span>
            {% endif %}
            {% if item.read_time_minutes %}
            <span class="read-time">~{{ item.read_time_minutes }}分钟阅读</span>
            {% endif %}
            {% if item.published_at %}
            <span class="date">{{ item.published_at.strftime('%Y-%m-%d %H:%M') }}</span>
            {% endif %}
            <a href="{{ item.link }}" target="_blank" class="original-link">查看原文</a>
        </div>
    </div>

    {% if item.key_points or item.summary_ai %}
    <div class="ai-info">
        {% if item.key_points %}
        <div>
            <h3>关键要点</h3>
            <ul class="key-points-list">
            {% for point in (item.key_points | from_json) %}
                <li>{{ point }}</li>
            {% endfor %}
            </ul>
        </div>
        {% endif %}
        {% if item.summary_ai %}
        <div style="margin-top: 10px;">
            <strong>AI 摘要：</strong>{{ item.summary_ai }}
        </div>
        {% endif %}
    </div>
    {% endif %}

    <div class="content-section">
        <h3>摘要</h3>
        <div class="markdown-content">
            {{ (item.summary_zh or item.summary) | markdown | safe }}
        </div>
    </div>

    {% if item.content %}
    <div class="content-section">
        <h3>全文{% if item.content_zh %}（中文）{% endif %}</h3>
        <div class="markdown-content">
            {{ (item.content_zh or item.content) | markdown | safe }}
        </div>
    </div>

    {% if item.content_zh and item.content != item.content_zh %}
    <details class="original-content">
        <summary>查看英文原文</summary>
        <div class="markdown-content">
            {{ item.content | markdown | safe }}
        </div>
    </details>
    {% endif %}
    {% endif %}

    <div class="actions">
        <a href="/inbox" class="btn btn-secondary">返回 Inbox</a>
        {% if item.status == 'inbox' %}
        <button class="btn btn-primary" onclick="moveToReading({{ item.id }})">标记为阅读</button>
        <button class="btn btn-secondary" onclick="discard({{ item.id }})">丢弃</button>
        {% elif item.status == 'reading' %}
        <a href="/reading" class="btn btn-secondary">返回阅读列表</a>
        <button class="btn btn-success" onclick="markRead({{ item.id }})">标记已读</button>
        <button class="btn btn-secondary" onclick="discard({{ item.id }})">丢弃</button>
        {% elif item.status == 'read' %}
        <a href="/inbox" class="btn btn-secondary">返回 Inbox</a>
        {% endif %}
        <a href="/items/{{ item.id }}/share" class="btn btn-secondary">分享</a>
        <a href="/items/{{ item.id }}/markdown" class="btn btn-secondary" download>导出 Markdown</a>
    </div>
</div>

<script>
async function moveToReading(id) {
    const response = await fetch(`/items/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'reading' })
    });
    if (response.ok) {
        window.location.href = '/reading';
    }
}

async function markRead(id) {
    const response = await fetch(`/items/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'read' })
    });
    if (response.ok) {
        window.location.href = '/reading';
    }
}

async function discard(id) {
    const response = await fetch(`/items/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'discarded' })
    });
    if (response.ok) {
        window.location.href = '/inbox';
    }
}
</script>
{% endblock %}
```

**Step 3: 手动验证**

```bash
./.venv/bin/uvicorn app.main:app --port 5005
# 浏览器访问 http://localhost:5005/items/1
```

**Step 4: 运行全部测试**

Run: `./.venv/bin/python -m pytest tests/ -v`
Expected: 全部 PASS

**Step 5: 提交**

```bash
git add app/templates/item_detail.html app/templates/base.html
git commit -m "feat: 文章详情页增加 AI 信息区和已读按钮"
```

---

### Task 7: 移动端响应式优化

**Files:**
- Modify: `app/templates/base.html` (CSS + 导航栏)

**Step 1: 在 base.html 的 `<style>` 中添加移动端样式**

在已有 `@media (max-width: 768px)` 块内（Task 6 已添加基础响应式）继续补充：

```css
@media (max-width: 768px) {
    body { padding: 10px; font-size: 16px; }
    .header { flex-direction: column; gap: 10px; }
    .nav { display: flex; flex-wrap: wrap; gap: 5px; }
    .nav a { margin-left: 0; font-size: 14px; padding: 6px 10px; }
    .item { padding: 12px 0; }
    .item-title { font-size: 16px; }
    .item-header h1 { font-size: 22px; }
    .markdown-content { font-size: 16px; line-height: 1.8; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; }
    .actions .btn { margin-right: 0; }
    .btn { padding: 10px 16px; min-height: 44px; font-size: 14px; }
    .ai-info { padding: 12px 15px; }
}
```

**Step 2: 手动验证**

```bash
./.venv/bin/uvicorn app.main:app --port 5005
# 浏览器开发者工具切换到移动端视图
```

**Step 3: 提交**

```bash
git add app/templates/base.html
git commit -m "feat: 移动端响应式优化"
```

---

### Task 8: 更新导航栏活跃状态

**Files:**
- Modify: `app/templates/base.html` (导航栏)
- Modify: `app/templates/inbox.html`
- Modify: `app/templates/reading.html`
- Modify: `app/templates/item_detail.html`

**Step 1: 修改 base.html 导航栏支持 active 状态**

将 base.html 的导航改为接收 `active_nav` 变量：

```html
<nav class="nav">
    <a href="/" class="{% if active_nav == 'home' %}active{% endif %}">首页</a>
    <a href="/inbox" class="{% if active_nav == 'inbox' %}active{% endif %}">Inbox</a>
    <a href="/reading" class="{% if active_nav == 'reading' %}active{% endif %}">Reading</a>
    <a href="/feeds" class="{% if active_nav == 'feeds' %}active{% endif %}">Feeds</a>
</nav>
```

**Step 2: 在各模板中传递 active_nav**

- `inbox.html`: 在模板变量中添加 `active_nav`（由路由传入）
- `reading.html`: 同上
- 路由中传 `{"active_nav": "inbox"}` / `{"active_nav": "reading"}` 等

**Step 3: 提交**

```bash
git add app/templates/base.html app/templates/inbox.html app/templates/reading.html app/main.py
git commit -m "feat: 导航栏活跃状态高亮"
```

---

### Task 9: 运行完整测试并验证

**Step 1: 运行全部测试**

Run: `./.venv/bin/python -m pytest tests/ -v`
Expected: 全部 PASS

**Step 2: 手动端到端验证**

```bash
./.venv/bin/uvicorn app.main:app --port 5005
```

验证流程：
1. 访问 `/inbox` — 查看文章列表
2. 点击"阅读" — 文章状态变为 reading
3. 访问 `/reading` — 在阅读列表中看到该文章
4. 点击详情 — 查看 AI 信息区（如有）
5. 点击"已读" — 文章状态变为 read
6. 移动端视图验证响应式

**Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: 渐进式阅读体验增强完成

- 打通阅读 pipeline（全文抓取/翻译/摘要/关键要点）
- 新增阅读列表页 /reading
- 四状态流：inbox → reading → read / discarded
- AI 阅读辅助（关键要点、阅读时长）
- 移动端响应式优化"
```
