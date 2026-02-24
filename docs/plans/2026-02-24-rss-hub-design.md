# RSS Hub 设计文档

**日期：** 2026-02-24
**目标：** 构建一个简单的RSS全文抓取工具，定时将RSS源的文章全文抓取并保存到SQLite数据库

## 需求概述

- 每天定时抓取RSS源的新文章
- 提取文章全文并转换为Markdown格式保存
- 使用SQLite数据库存储
- 根据标题+URL去重
- 失败不影响其他源的处理

## 架构设计

### 模块结构

```
RssHub/
├── config.py          # 配置管理（读取YAML、数据库路径）
├── fetcher.py         # RSS和网页抓取（feedparser + trafilatura）
├── storage.py         # SQLite操作（建表、插入、去重）
├── main.py            # 主入口（调度、日志）
├── sources.yaml       # RSS源配置
├── rss.db            # SQLite数据库
└── requirements.txt   # 依赖列表
```

### 模块职责

| 模块 | 职责 |
|------|------|
| `config.py` | 读取YAML配置文件，提供配置接口 |
| `fetcher.py` | 解析RSS feed，使用trafilatura提取网页正文转Markdown |
| `storage.py` | SQLite数据库操作：建表、插入、去重查询 |
| `main.py` | 主流程控制、日志记录、错误处理 |

## 数据库设计

### articles 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 自增ID |
| title | TEXT | 文章标题 |
| url | TEXT UNIQUE | 文章链接（唯一约束） |
| source | TEXT | RSS源名称 |
| content | TEXT | 文章正文（Markdown格式） |
| published_at | TIMESTAMP | 发布时间 |
| fetched_at | TIMESTAMP | 抓取时间 |

### 去重逻辑

- URL作为唯一约束（UNIQUE）
- 插入前先查询URL是否存在
- 若存在则跳过，避免重复抓取

## 核心流程

```
1. 加载 sources.yaml 配置
2. 初始化数据库连接
3. 对每个RSS源：
   a. 解析RSS feed
   b. 对每篇文章：
      - 检查数据库是否已存在（URL去重）
      - 如果RSS有完整content → 直接使用
      - 如果只有summary → 用trafilatura抓取网页转MD
      - 存入数据库
   c. 失败则记录日志，继续处理下一个源
4. 输出统计信息（新增文章数、跳过数、失败源）
```

## 技术选型

| 依赖 | 用途 | 理由 |
|------|------|------|
| feedparser | RSS解析 | 成熟稳定，支持各种RSS格式 |
| trafilatura | 网页正文提取 | 专门提取正文，输出Markdown，轻量（~1MB） |
| httpx | HTTP请求 | 现代异步HTTP客户端，API友好 |
| pyyaml | YAML解析 | 解析sources.yaml配置文件 |

## 配置文件格式

### sources.yaml

```yaml
sources:
  - name: "技术博客名称"
    url: "https://example.com/rss"

  - name: "新闻网站"
    url: "https://news.example.com/feed"
```

## 错误处理

- **RSS解析失败：** 记录错误日志，跳过该源，继续处理其他源
- **网页抓取失败：** 记录URL，使用RSS摘要作为fallback
- **数据库操作失败：** 记录详细错误信息

## 定时任务

使用 cron 每天定时执行：

```bash
# 每天 8:00 执行
0 8 * * * cd /home/ubuntu/PyProjects/RssHub && ./.venv/bin/python main.py >> cron.log 2>&1
```

## 日志策略

- 输出到stdout，由cron重定向到cron.log
- 包含：抓取开始时间、每个源的处理结果、统计信息
- 格式：`[时间] [级别] 消息`
