# RssHub 开发路线图（按当前代码真实状态）

> 更新时间：2026-03-25
>
> 说明：本文件基于当前仓库代码和本地测试结果整理，描述的是“实际状态”，不是目标状态。

## 当前状态概览

项目已经有可运行的 FastAPI 骨架、数据库模型、RSS 同步链路和基础页面，但整体仍处于“后端雏形 + 部分功能接通”的阶段。

当前最接近可用的主流程是：

1. 创建/更新/删除 RSS 源
2. 通过定时任务或 `POST /sync` 同步全部启用源
3. 抓取 RSS 条目并去重
4. 对标题和摘要做翻译与摘要级评分
5. 在 Inbox 中查看文章并修改状态
6. 导出 Markdown

当前最明显的问题是：

- 分享页面路由存在，但当前会因为模板过滤器未注册而报错
- 单个 RSS 源同步仍是占位实现
- 文章状态更新后没有触发全文抓取、翻译、总结或偏好学习
- 全文抓取、AI 总结、偏好学习、向量推荐都还没有真正接入主流程
- 前端只有 Inbox 和 Share 模板，没有 Reading 页，也没有 HTML 版文章详情页

---

## 已实现且已接通的功能

| 模块 | 当前状态 | 说明 |
|------|----------|------|
| RSS 源管理 API | ✅ | `GET/POST/PATCH/DELETE /feeds` 已实现 |
| 全量同步入口 | ✅ | 调度器定时同步 + `POST /sync` 手动同步全部启用源 |
| RSS 抓取 | ✅ | 能抓取 feed、解析条目、生成 `dedupe_key`、做 HTML -> Markdown |
| 去重入库 | ✅ | 同步流程会按 `dedupe_key` 去重并写入 `items` |
| 标题/摘要翻译 | ✅ | 在调度器同步流程中调用 `Translator` |
| 摘要级评分 | ✅ | 在调度器同步流程中调用 `Scorer`，但用户偏好目前固定为空字符串 |
| 文章列表 API | ✅ | `GET /items` 支持按状态筛选 |
| 单篇文章 API | ✅ | `GET /items/{id}` 已实现，返回 JSON |
| 文章状态更新 API | ✅ | `PATCH /items/{id}` 已实现，但只更新状态字段 |
| Markdown 导出 | ✅ | `POST /exports/items/{id}/markdown` 可用 |
| Inbox 页面 | ✅ | `/inbox` 可渲染文章列表页面 |
| 数据模型与 ORM | ✅ | `Feed`、`Item`、`Preference`、`Share` 模型已定义 |

---

## 已存在代码，但未真正完成或未接入主流程

### 1. 单个 RSS 源手动同步

- `POST /feeds/{feed_id}/sync` 路由已存在
- 目前只有查询 feed 和返回占位响应
- 实际抓取、去重、入库、更新时间都没有实现

### 2. 文章状态更新后的自动处理

- `PATCH /items/{id}` 当前只会写入 `status`
- 标记为 `reading` 后没有触发：
  - 全文抓取
  - 全文翻译
  - AI 总结
  - 全文评分
- 标记为 `discarded` 后也没有触发偏好学习

### 3. 全文抓取

- `app/services/content_fetcher.py` 已实现 `ContentFetcher`
- 当前同步流程和状态更新流程都没有调用它
- `Item.content` / `Item.content_zh` 字段目前主要还是预留

### 4. AI 总结

- `app/services/summarizer.py` 已实现 `Summarizer`
- 当前没有任何主流程调用它
- `Item.summary_ai` 在真实流程里不会自动生成

### 5. 偏好学习

- `extract_keywords` 已实现基础关键词提取
- `get_user_preferences` 目前返回硬编码字符串，不是从数据库聚合
- `learn_from_feedback` 仍是空实现
- 调度器评分时传入的 `user_preferences` 目前固定为空字符串

### 6. 向量存储和推荐

- `Item` 模型中已有 `embedding_id`
- `pyproject.toml` 已声明 `chromadb`
- 当前没有 Embedding 调用、向量写入、相似度检索或推荐逻辑

---

## 已知故障和不一致

### 1. 分享页面当前不可用

- `GET /shares/{code}` 路由存在
- 但该路由内部重新创建了一个新的 `Jinja2Templates`
- 新实例没有注册 `markdown` 过滤器
- `share.html` 又依赖 `markdown` 过滤器渲染内容
- 因此访问分享页面时会触发模板错误，而不是正常展示页面

### 2. 获取分享链接接口语义不正确

- `GET /shares/items/{item_id}` 当前返回的是 `{"share_url": "/share/{item_id}"}` 这种占位路径
- 它没有读取真实 `share_code`
- 返回路径格式也与实际分享页路由 `/shares/{code}` 不一致

### 3. 分享过期未校验

- `Share` 模型中有 `expires_at`
- 但 `GET /shares/{code}` 当前只按 `share_code` 查找，不判断是否过期

### 4. 前端导航和实际页面不一致

- 顶部导航里有 `/reading`
- 但当前没有该路由，也没有对应模板
- Inbox 里的“详情”按钮会跳到 `/items/{id}`
- 该地址返回 JSON，不是 HTML 页面
- 导航里的 `/feeds` 也是 JSON API，不是管理页面

---

## 前端页面真实状态

| 页面/入口 | 当前状态 | 说明 |
|-----------|----------|------|
| `/inbox` | ✅ | 已实现 HTML 页面 |
| `/shares/{code}` | ⚠️ | 路由存在，但当前渲染会报错 |
| `/reading` | ❌ | 路由不存在 |
| `/items/{id}` HTML 详情页 | ❌ | 只有 JSON API，没有模板页面 |
| `/feeds` 管理页 | ❌ | 只有 JSON API，没有页面 |

---

## 路由实现状态表

| 路由 | 状态 | 当前真实情况 |
|------|------|--------------|
| `GET /` | ✅ | 返回基础信息 JSON |
| `GET /health` | ✅ | 健康检查 |
| `GET /debug/scheduler` | ✅ | 调试调度器状态 |
| `POST /sync` | ✅ | 手动触发同步全部启用源 |
| `GET /inbox` | ✅ | Inbox HTML 页面 |
| `GET /feeds` | ✅ | 获取 RSS 源列表（JSON） |
| `POST /feeds` | ✅ | 创建 RSS 源 |
| `PATCH /feeds/{id}` | ✅ | 更新 RSS 源 |
| `DELETE /feeds/{id}` | ✅ | 删除 RSS 源 |
| `POST /feeds/{id}/sync` | ⚠️ | 路由存在，但同步逻辑未实现 |
| `GET /items` | ✅ | 获取文章列表（JSON） |
| `GET /items/{id}` | ✅ | 获取单篇文章（JSON） |
| `PATCH /items/{id}` | ⚠️ | 只更新状态，不触发后续任务 |
| `POST /shares/items/{id}` | ✅ | 创建分享记录 |
| `GET /shares/items/{id}` | ⚠️ | 返回占位分享路径，不是实际可用链接 |
| `GET /shares/{code}` | ⚠️ | 路由存在，但当前页面渲染失败 |
| `POST /exports/items/{id}/markdown` | ✅ | Markdown 导出可用 |
| `GET /reading` | ❌ | 不存在 |

---

## 技术栈接入状态

| 组件 | 状态 | 说明 |
|------|------|------|
| FastAPI | ✅ | 应用和路由基础已搭好 |
| SQLAlchemy Async | ✅ | 异步数据库访问已接通 |
| SQLite | ✅ | 当前默认数据库 |
| APScheduler | ✅ | 定时同步已接通 |
| Jinja2 | ✅ | Inbox 页面可用，Share 页面当前有集成问题 |
| httpx | ✅ | 已用于 RSS 抓取和 LLM/API 调用 |
| feedparser | ✅ | 已用于 RSS 解析 |
| markdownify | ✅ | 已用于 HTML 转 Markdown |
| markdown | ✅ | 已用于模板渲染 Markdown |
| jieba | ✅ | 已用于基础关键词提取 |
| ChromaDB | ⚠️ | 仅安装，未接入业务 |

---

## 本地验证结果

已运行：

```bash
uv run pytest tests/test_items_route.py tests/test_feeds_route.py tests/test_e2e.py -q
```

结果：

- 15 个测试通过
- 2 个测试失败
- 失败点都在分享页面渲染，说明分享功能目前不能算“完成”

---

## 建议的开发优先级

### P0

1. 修复分享页面渲染问题
2. 修正 `GET /shares/items/{id}` 的返回语义，返回真实可访问分享地址
3. 实现文章状态更新后的自动处理链路

### P1

1. 实现单个 RSS 源同步
2. 增加 HTML 版文章详情页
3. 增加 Reading 页面

### P2

1. 完成偏好学习落库与聚合
2. 在评分阶段接入真实用户偏好
3. 为分享链接增加过期校验

### P3

1. 接入 Embedding API
2. 接入 ChromaDB
3. 实现相似文章推荐
