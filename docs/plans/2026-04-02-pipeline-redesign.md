# RSS 流水线重构设计

## 背景

当前架构中，RSS 抓取、翻译、评分、全文抓取分散在多个触发点（定时任务 + 用户交互）。翻译功能不再需要，状态机过于复杂。需要统一为每天一次的定时流水线。

## 目标

将整个处理流程改为**单次定时流水线**：抓取 RSS → 摘要评分 → 按分数排序 → 抓取全文 → 全文评分 → 生成摘要，每天 0 点执行一次。

## 新流程

```
sync_feeds() 线性流水线:

阶段1 - RSS 抓取 + 摘要评分（轻量）
  for feed in enabled_feeds:
    items = rss_fetcher.fetch(feed.url)
    for item in items:
      去重 → 入库 (status=unread)
      score_summary = scorer.score(title, summary)

阶段2 - 全文抓取 + 全文评分（重量级，按分数排序）
  candidates = SELECT * FROM items WHERE score_full IS NULL
               ORDER BY score_summary DESC
  for item in candidates:
    content = content_fetcher.fetch(item.link)  # 三级降级
    if content:
      article_store.save(item, content)          # 保存 md 文件
      item.content = content
      item.score_full = scorer.score_full(title, content[:4000])
      item.summary_ai = summarizer.summarize(content[:4000])
      item.key_points = extract_key_points(content[:4000])
      item.read_time_minutes = estimate(content)
    await session.commit()  # 每篇独立提交
```

## 改动清单

### 1. 新建 `app/services/article_store.py`

负责将全文保存为 Markdown 文件。

- 路径格式：`articles/YYYY-MM-DD/{slug}.md`
- slug 生成：标题 → 小写 → 非字母数字替换为 `-` → 截断 80 字符 → 去重复 `-`
- 文件格式：frontmatter（title, link, published_at, feed, score_summary, score_full, read_time_minutes）+ 正文
- 同名冲突：追加 `-2`, `-3`

### 2. 改造 `app/services/scorer.py`

新增 `score_full(title, content)` 方法：
- 输入 title + 全文（截断 4000 字符）
- 使用与 `score()` 相同的四维评分标准
- 输出 0-100 分

### 3. 改造 `app/services/scheduler.py`

重写 `sync_feeds()` 为上述两阶段流水线：
- 阶段1：抓 RSS + 摘要评分（保持现有逻辑，去掉翻译调用）
- 阶段2：查询所有未全文评分的文章，按 score_summary 降序，依次抓取全文、评分、生成摘要
- 每篇文章独立事务，失败不影响后续

### 4. 改造 `app/models.py`

- 新增 `article_path` 字段（String，存储相对路径）
- 删除 `title_zh`, `summary_zh`, `content_zh` 字段
- 状态字段改为 `unread` / `read`（默认 `unread`）

### 5. 改造 `app/routes/items.py`

- 去掉 `_run_pipeline` 函数和 ReadingPipeline 调用
- PATCH 只支持 `read` 状态切换
- 保留 discarded 状态的偏好记录逻辑

### 6. 改造 `app/main.py`

- `/inbox` 改为 `/`（主页）
- 去掉 `/reading` 路由
- 主页查询改为 `status=unread`，按 `score_full` 降序

### 7. 改造前端模板

- `inbox.html` → `home.html`（主页，展示 unread 列表）
- 去掉 `reading.html`
- 去掉翻译相关显示（title_zh, summary_zh, content_zh）
- 排序改用 `score_full`（无 score_full 时 fallback 到 score_summary）
- `item_detail.html` 去掉翻译内容，优先展示 article_path 对应的 Markdown

### 8. 删除文件

- `app/services/translator.py`
- `app/services/reading_pipeline.py`

## 不变的部分

- `app/services/rss_fetcher.py` — RSS 解析逻辑不变
- `app/services/content_fetcher.py` — 三级降级抓取策略不变
- `app/services/summarizer.py` — AI 摘要逻辑不变
- `app/services/preference.py` — 偏好记录不变
- `app/routes/feeds.py` — Feed CRUD 不变
- `app/routes/exports.py` — Markdown 导出不变
- `app/routes/shares.py` — 分享系统不变
