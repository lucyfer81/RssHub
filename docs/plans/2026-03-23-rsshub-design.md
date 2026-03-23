# RssHub 设计文档

## 概述

RssHub 是一个个人 RSS 订阅管理系统，用 Python 重写 dotrss 项目。核心功能包括 RSS 同步、AI 评分、翻译、总结、偏好学习和内容分享。

## 技术栈

| 类别 | 选型 |
|------|------|
| Web 框架 | FastAPI |
| 数据库 | SQLite + SQLAlchemy |
| 向量库 | ChromaDB |
| 定时任务 | APScheduler |
| 模板引擎 | Jinja2 |
| HTTP 客户端 | httpx (异步) |
| RSS 解析 | feedparser |
| 全文抓取 | Jina.ai Reader API |
| 包管理 | uv |

## 架构设计

单体分层架构：

```
┌─────────────────────────────────────────┐
│              FastAPI App                │
├─────────────────────────────────────────┤
│  Routes → Services → Models (SQLite)    │
│  APScheduler (后台任务)                  │
│  Chroma (向量存储)                       │
│  Jinja2 Templates (简单前端)             │
└─────────────────────────────────────────┘
```

## 项目结构

```
RssHub/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── database.py          # SQLite 连接
│   ├── models.py            # SQLAlchemy 模型
│   ├── schemas.py           # Pydantic 模型
│   ├── routes/
│   │   ├── feeds.py         # RSS 源管理 API
│   │   ├── items.py         # 文章管理 API
│   │   ├── shares.py        # 分享链接 API
│   │   └── exports.py       # 导出 API
│   ├── services/
│   │   ├── rss_fetcher.py   # RSS 抓取
│   │   ├── content_fetcher.py # 全文抓取 (Jina.ai)
│   │   ├── translator.py    # LLM 翻译
│   │   ├── scorer.py        # AI 评分
│   │   ├── summarizer.py    # AI 总结
│   │   ├── preference.py    # 偏好学习
│   │   └── scheduler.py     # APScheduler 任务
│   └── templates/           # Jinja2 模板
│       ├── base.html
│       ├── inbox.html
│       ├── reading.html
│       ├── feed_list.html
│       └── share.html
├── chroma_db/               # Chroma 向量库
├── data/
│   └── rss.db               # SQLite 数据库
├── .env
├── pyproject.toml
└── README.md
```

## 数据库设计

### feeds 表 - RSS 源

```sql
CREATE TABLE feeds (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 1,
    last_synced_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### items 表 - 文章条目

```sql
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    feed_id INTEGER NOT NULL,

    -- 原始内容
    title TEXT NOT NULL,
    link TEXT NOT NULL UNIQUE,
    summary TEXT,
    published_at DATETIME,

    -- 翻译内容
    title_zh TEXT,
    summary_zh TEXT,

    -- 全文内容 (筛选后抓取)
    content TEXT,
    content_zh TEXT,
    summary_ai TEXT,

    -- 评分
    score_summary REAL,        -- 基于摘要的评分
    score_full REAL,           -- 基于全文的评分

    -- 状态
    status TEXT DEFAULT 'inbox', -- inbox/reading/discarded

    -- 向量
    embedding_id TEXT,

    -- 去重
    dedupe_key TEXT UNIQUE,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### preferences 表 - 用户偏好

```sql
CREATE TABLE preferences (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL,
    feedback TEXT NOT NULL,    -- approved/discarded
    keywords TEXT,             -- 提取的关键词 (JSON)
    score_diff REAL,           -- score_summary 与 score_full 的差异
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### shares 表 - 分享链接

```sql
CREATE TABLE shares (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL,
    share_code TEXT NOT NULL UNIQUE,
    expires_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 核心业务流程

### 流程 1：RSS 同步（定时任务）

```
1. 遍历所有启用的 feeds
2. 抓取 RSS，解析新文章
3. 去重检查（dedupe_key）
4. 存储：title, summary, link, published_at
5. 调用 LLM 翻译 → title_zh, summary_zh
6. 调用 AI 评分 → score_summary（基于偏好）
7. 存入向量库 → embedding_id
```

### 流程 2：用户筛选

```
用户在 Inbox 浏览（按 score_summary 降序）
  ↓
点击"阅读" → status = 'reading'
  ↓
触发后台任务：
  - 抓取全文 (Jina.ai) → content
  - 翻译全文 → content_zh
  - AI 总结 → summary_ai
  - 重新评分 → score_full
  - 对比 score_summary vs score_full，学习差异
  ↓
用户在 Reading 队列阅读

或

点击"丢弃" → status = 'discarded'
  ↓
记录偏好学习
```

### 流程 3：偏好学习

```
1. 用户筛选动作触发：
   - reading → 提取关键词，标记为"喜欢"
   - discarded → 提取关键词，标记为"不喜欢"

2. 全文评分完成后：
   - 对比 score_summary 和 score_full
   - 如果差异大，提取全文关键特征
   - 存入 preferences 表（带权重）

3. 定期聚合偏好，更新评分提示词

4. 下次摘要评分时，AI 会更关注强化特征
```

## API 设计

### Feeds 管理

```
GET    /feeds                 # 获取所有 RSS 源
POST   /feeds                 # 添加 RSS 源
PUT    /feeds/{id}            # 更新 RSS 源
DELETE /feeds/{id}            # 删除 RSS 源
POST   /feeds/{id}/sync       # 手动同步某个源
POST   /feeds/sync-all        # 手动同步所有源
```

### Items 管理

```
GET    /items                 # 获取文章列表（支持 status 筛选）
GET    /items/{id}            # 获取文章详情
PATCH  /items/{id}            # 更新状态
POST   /items/{id}/fetch-full # 手动触发抓取全文
GET    /items/search          # 搜索文章
```

### AI 手动控制

```
POST   /items/{id}/translate  # 手动重新翻译
POST   /items/{id}/summarize  # 手动重新总结
POST   /items/{id}/score      # 手动重新评分
```

### 分享与导出

```
POST   /items/{id}/share      # 生成分享链接
GET    /share/{code}          # 公开访问分享页面
POST   /items/{id}/export     # 导出为 Markdown 文件
```

### 系统

```
GET    /stats                 # 统计信息
GET    /preferences           # 查看学习到的偏好
POST   /preferences/reset     # 重置偏好学习
```

## 前端页面

| 页面 | 路径 | 功能 |
|------|------|------|
| Inbox | `/inbox` | 待筛选文章，按 score_summary 降序 |
| Reading | `/reading` | 待阅读文章，按 score_full 降序 |
| Discarded | `/discarded` | 已丢弃文章 |
| 文章详情 | `/items/{id}` | 阅读文章，支持原文/译文/总结切换 |
| 分享页面 | `/share/{code}` | 公开访问的文章页面 |
| Feed 管理 | `/feeds` | 管理 RSS 源 |
| 设置 | `/settings` | 偏好查看、系统配置 |

## 配置项

```bash
# 数据库
DATABASE_URL=sqlite:///./data/rss.db
CHROMA_PERSIST_DIR=./chroma_db

# LLM API
LLM_BASE_URL=https://api.edgefn.net/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=Qwen3-Next-80B-A3B-Instruct

# Embedding API
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=sk-xxx
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
SHARE_BASE_URL=https://your-domain.com/share
```

## 依赖清单

```toml
[project]
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
```
