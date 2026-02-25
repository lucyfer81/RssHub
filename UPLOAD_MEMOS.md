# 上传文章到 Memos Worker

这个脚本可以将本地 RSS 数据库中的文章批量上传到 [memos-worker](https://memos.aizhi.app)。

## 配置

1. 复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，填入你的配置：

```ini
MEMOS_API_URL=https://memos.aizhi.app
RSS_INGEST_TOKEN=your_token_here
```

- `MEMOS_API_URL`: 你的 memos-worker 地址
- `RSS_INGEST_TOKEN`: 在 memos-worker 环境变量中配置的 `RSS_INGEST_TOKEN`

## 使用方法

### 基本用法

上传所有文章：

```bash
./.venv/bin/python upload_to_memos.py
```

### 常用选项

| 选项 | 说明 |
|------|------|
| `--source, -s` | 只上传指定源的文章 |
| `--limit, -l` | 限制上传的文章数量 |
| `--batch-size, -b` | 每批上传的数量（默认：20） |
| `--dry-run, -n` | 试运行模式，不实际上传 |

### 示例

试运行（查看会上传什么）：

```bash
./.venv/bin/python upload_to_memos.py --dry-run
```

只上传 Hugging Face Blog 的文章：

```bash
./.venv/bin/python upload_to_memos.py --source "Hugging Face Blog"
```

先测试上传 10 篇：

```bash
./.venv/bin/python upload_to_memos.py --limit 10
```

## 特性

- **自动去重**: 根据 URL 自动去重，已存在的文章会被跳过或更新
- **批量处理**: 支持大批量文章上传
- **增量同步**: 可以多次运行，只处理新文章
- **自动文件夹**: 文章会自动保存到 `PARA/Areas/Reading/RSS/<feed>/` 文件夹

## 输出示例

```
==================================================
RSS → Memos 上传工具
==================================================
API 地址: https://memos.aizhi.app
数据库: /home/ubuntu/PyProjects/RssHub/rss.db
批次大小: 20

从数据库读取文章...
找到 1080 篇文章
转换数据格式...

开始上传...
处理批次 1/54 (20 篇文章)...
  ✓ 批次完成: 新增 20 | 更新 0 | 跳过 0 | 失败 0
处理批次 2/54 (20 篇文章)...
  ✓ 批次完成: 新增 20 | 更新 0 | 跳过 0 | 失败 0
...

==================================================
上传完成
==================================================
总数: 1080
成功: 1080
跳过: 0
失败: 0
```
