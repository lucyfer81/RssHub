# RSS Hub

强大的 RSS 全文抓取与管理工具，支持将 RSS 文章保存到本地数据库，并可选择性上传到 Memos。

## ✨ 功能特性

- 📡 **多 RSS 源管理** - 在 `sources.yaml` 中统一管理所有订阅源
- 🌐 **全文抓取** - 自动抓取网页正文并转换为 Markdown 格式
- 💾 **SQLite 存储** - 本地数据库持久化存储文章
- 🔗 **自动去重** - 根据 URL 自动去重，避免重复文章
- 🔄 **智能重试** - 指数退避重试机制，处理 429 速率限制
- 🛡️ **403 错误处理** - 遇到 403 时自动使用 RSS 摘要作为回退
- 📤 **可选上传** - 支持将文章上传到 Memos (需要配置)
- 📊 **详细日志** - 清晰的日志输出，便于调试
- ✅ **容错机制** - 单个源失败不影响其他源

## 📦 安装

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd RssHub

# 2. 使用 uv 安装依赖（推荐）
uv pip install -r requirements.txt

# 或使用传统方式
pip install -r requirements.txt
```

## ⚙️ 配置

### 1. 配置 RSS 源

编辑 `sources.yaml` 添加你想要的 RSS 源：

```yaml
sources:
  - name: "Anthropic Engineering"
    url: "https://raw.githubusercontent.com/conoro/anthropic-engineering-rss-feed/main/anthropic_engineering_rss.xml"

  - name: "Andrej Karpathy"
    url: "https://karpathy.bearblog.dev/feed/"

  - name: "Simon Willison"
    url: "https://simonwillison.net/atom/everything/"
```

### 2. 配置 Memos 上传（可选）

如果你想要上传到 Memos，创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# Memos API 地址
MEMOS_API_URL=https://memos.aizhi.app

# RSS Ingest Token（从 Memos 获取）
RSS_INGEST_TOKEN=your_token_here
```

## 🚀 使用

### 模式一：仅下载文章（推荐新手）

只将文章下载到本地数据库，不上传到任何地方。

```bash
# 运行主程序，抓取所有 RSS 源
./.venv/bin/python main.py
```

**查看抓取的文章：**

```bash
# 查看最新 10 篇文章
sqlite3 rss.db "SELECT title, source, published_at FROM articles ORDER BY published_at DESC LIMIT 10;"

# 统计每个源的文章数量
sqlite3 rss.db "SELECT source, COUNT(*) as count FROM articles GROUP BY source ORDER BY count DESC;"

# 搜索特定文章
sqlite3 rss.db "SELECT title, url FROM articles WHERE title LIKE '%AI%';"
```

**设置定时任务：**

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每天 8:00 执行）
0 8 * * * cd /home/ubuntu/PyProjects/RssHub && ./.venv/bin/python main.py >> cron.log 2>&1
```

---

### 模式二：下载 + 上传到 Memos

先下载文章到本地，然后上传到 Memos。

**步骤 1：下载文章**

```bash
./.venv/bin/python main.py
```

**步骤 2：上传到 Memos**

```bash
# 上传所有新文章
./.venv/bin/python upload_to_memos.py

# 只上传特定源
./.venv/bin/python upload_to_memos.py --source "Andrej Karpathy"

# 限制上传数量（测试用）
./.venv/bin/python upload_to_memos.py --limit 5

# 试运行（不实际上传）
./.venv/bin/python upload_to_memos.py --dry-run

# 重置上传记录（强制重新上传所有）
./.venv/bin/python upload_to_memos.py --reset-tracker
```

**一键下载+上传：**

```bash
# 先下载再上传
./.venv/bin/python main.py && ./.venv/bin/python upload_to_memos.py
```

---

### 模式三：测试工具

**测试 RSS 源是否可用：**

```bash
./.venv/bin/python test_sources.py
```

输出示例：
```
测试: Andrej Karpathy
URL: https://karpathy.bearblog.dev/feed/
状态: ✓ 可访问
文章数量: 10
内容字段: 有
```

## 📁 项目结构

```
RssHub/
├── main.py                  # 主入口：下载文章
├── upload_to_memos.py       # 上传到 Memos
├── test_sources.py          # 测试 RSS 源
├── fetcher.py               # RSS 和网页抓取逻辑
├── storage.py               # 数据库操作
├── sources.yaml             # RSS 源配置
├── requirements.txt         # 依赖列表
├── .env.example             # 环境变量示例
├── rss.db                   # SQLite 数据库（自动生成）
├── .upload_tracker.db       # 上传记录（自动生成）
└── README.md                # 本文档
```

## 🔧 常用命令

### 下载文章相关

```bash
# 手动运行一次
./.venv/bin/python main.py

# 查看日志
tail -f rss.log

# 测试某个源
./.venv/bin/python test_sources.py
```

### 数据库查询

```bash
# 进入数据库
sqlite3 rss.db

# 查看所有表
.tables

# 查看最新文章
SELECT title, source, published_at FROM articles ORDER BY published_at DESC LIMIT 10;

# 查看某个源的文章
SELECT * FROM articles WHERE source = 'Andrej Karpathy' ORDER BY published_at DESC;

# 统计信息
SELECT source, COUNT(*) as count FROM articles GROUP BY source ORDER BY count DESC;

# 退出
.quit
```

### 上传相关

```bash
# 查看上传状态
sqlite3 .upload_tracker.db "SELECT source, COUNT(*) as count FROM uploaded_memos GROUP BY source;"

# 查看最近上传
sqlite3 .upload_tracker.db "SELECT * FROM uploaded_memos ORDER BY updated_at DESC LIMIT 10;"

# 重置上传记录（强制重新上传）
rm .upload_tracker.db
```

## 🎯 推荐工作流

### 方案 A：只保存到本地（简单）

```bash
# 1. 配置 sources.yaml
vim sources.yaml

# 2. 运行一次测试
./.venv/bin/python main.py

# 3. 设置定时任务
crontab -e
# 添加: 0 8 * * * cd /home/ubuntu/PyProjects/RssHub && ./.venv/bin/python main.py >> cron.log 2>&1

# 4. 需要时查询数据库
sqlite3 rss.db
```

### 方案 B：本地 + Memos（完整）

```bash
# 1. 配置 sources.yaml
vim sources.yaml

# 2. 配置 .env
cp .env.example .env
vim .env

# 3. 测试 RSS 源
./.venv/bin/python test_sources.py

# 4. 下载文章
./.venv/bin/python main.py

# 5. 测试上传（不实际执行）
./.venv/bin/python upload_to_memos.py --dry-run

# 6. 上传到 Memos
./.venv/bin/python upload_to_memos.py

# 7. 设置一键脚本
cat > sync.sh << 'EOF'
#!/bin/bash
cd /home/ubuntu/PyProjects/RssHub
./.venv/bin/python main.py && ./.venv/bin/python upload_to_memos.py
EOF
chmod +x sync.sh

# 8. 设置定时任务
crontab -e
# 添加: 0 8 * * * cd /home/ubuntu/PyProjects/RssHub && ./sync.sh >> cron.log 2>&1
```

## 🐛 故障排查

### 问题 1：某个源抓取失败

```bash
# 测试该源
./.venv/bin/python test_sources.py

# 查看日志
tail -100 rss.log | grep "源名称"
```

### 问题 2：上传失败

```bash
# 检查环境变量
cat .env

# 试运行查看详情
./.venv/bin/python upload_to_memos.py --dry-run

# 重置上传记录重试
./.venv/bin/python upload_to_memos.py --reset-tracker
```

### 问题 3：代理问题

```bash
# 设置代理
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890

# 或在 .env 中配置
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

## 📊 数据库字段说明

### articles 表

| 字段 | 说明 |
|------|------|
| id | 自增主键 |
| title | 文章标题 |
| url | 文章链接（作为唯一标识） |
| source | RSS 源名称 |
| content | 文章正文（Markdown 格式） |
| published_at | 发布时间 |
| created_at | 抓取时间 |
| fetch_method | 抓取方式（rss_content/rss_summary/fetched 等） |

### uploaded_memos 表

| 字段 | 说明 |
|------|------|
| id | 自增主键 |
| source | RSS 源名称 |
| url | 文章链接 |
| title | 文章标题 |
| content_hash | 内容哈希（用于检测更新） |
| memo_id | Memos 中的笔记 ID |
| created_at | 首次上传时间 |
| updated_at | 最后更新时间 |

## 📝 开发说明

### 添加新功能

1. **添加新的 RSS 源**：编辑 `sources.yaml`
2. **修改抓取逻辑**：编辑 `fetcher.py`
3. **修改存储逻辑**：编辑 `storage.py`
4. **修改上传逻辑**：编辑 `upload_to_memos.py`

### 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License
