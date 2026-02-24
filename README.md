# RSS Hub

简单的RSS全文抓取工具，定时将RSS源的文章全文抓取并保存到SQLite数据库。

## 功能特性

- 支持多个RSS源配置
- 自动抓取网页全文并转换为Markdown格式
- SQLite数据库存储
- 根据URL自动去重
- 详细的日志输出
- 单个源失败不影响其他源

## 安装

```bash
# 安装依赖
uv pip install -r requirements.txt
```

## 配置

编辑 `sources.yaml` 添加RSS源:

```yaml
sources:
  - name: "技术博客"
    url: "https://blog.example.com/rss"

  - name: "新闻网站"
    url: "https://news.example.com/feed"
```

## 使用

### 手动运行

```bash
python main.py
```

### 定时任务

使用cron每天定时执行:

```bash
# 编辑crontab
crontab -e

# 添加以下行（每天8:00执行）
0 8 * * * cd /home/ubuntu/PyProjects/RssHub && ./.venv/bin/python main.py >> cron.log 2>&1
```

## 数据库

数据保存在 `rss.db` SQLite文件中。

### 查询文章

```bash
sqlite3 rss.db "SELECT title, url, source, published_at FROM articles ORDER BY published_at DESC LIMIT 10;"
```

### 统计信息

```bash
sqlite3 rss.db "SELECT source, COUNT(*) as count FROM articles GROUP BY source ORDER BY count DESC;"
```

## 项目结构

```
RssHub/
├── config.py          # 配置管理
├── fetcher.py         # RSS和网页抓取
├── storage.py         # 数据库操作
├── main.py            # 主入口
├── sources.yaml       # RSS源配置
├── rss.db            # SQLite数据库
└── requirements.txt   # 依赖列表
```
