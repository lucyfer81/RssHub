# RssHub

个人 RSS 订阅管理系统，支持 AI 评分、翻译、总结和偏好学习。

## 功能特性

- 📡 **RSS 源管理** - 添加、编辑、删除 RSS 订阅源
- 🔄 **自动同步** - 定时抓取 RSS 更新
- 🤖 **AI 智能评分** - 基于个人偏好对文章进行 0-100 评分
- 🌍 **自动翻译** - 中英文自动翻译
- 📝 **AI 总结** - 生成文章摘要
- 📚 **全文抓取** - 使用 Jina.ai Reader API 抓取完整文章内容
- 💡 **偏好学习** - 根据阅读行为优化推荐
- 🔗 **分享链接** - 生成可公开访问的文章页面
- 📥 **Markdown 导出** - 导出文章为 Markdown 文件

## 技术栈

- **Web 框架**: FastAPI
- **数据库**: SQLite + SQLAlchemy (异步)
- **向量库**: ChromaDB
- **定时任务**: APScheduler
- **全文抓取**: Jina.ai Reader API
- **LLM API**: 兼容 OpenAI 格式的 API

## 安装

```bash
# 克隆项目
git clone <repo-url>
cd RssHub

# 安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate
```

## 配置

复制 `.env.example` 为 `.env`，填入你的配置：

```bash
cp .env.example .env
```

必需的配置项：

```bash
# LLM API
LLM_BASE_URL=https://api.openai.com/v1  # 或兼容的 API
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4

# Embedding API
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-ada-002
```

## 运行

```bash
# 初始化数据库
uv run python -c "from app.database import init_db; import asyncio; asyncio.run(init_db())"

# 初始化 RSS 源（可选）
uv run python scripts/init_feeds.py

# 启动服务
uv run python -m app.main
```

访问 http://localhost:8000

## 使用流程

1. **添加 RSS 源** - 访问 `/feeds` 添加你感兴趣的 RSS 源
2. **等待同步** - 定时任务会自动抓取新文章
3. **查看 Inbox** - 在 `/inbox` 查看按评分排序的文章
4. **筛选文章** - 点击"阅读"或"丢弃"来训练偏好模型
5. **阅读文章** - 系统自动抓取全文、翻译并总结

## API 文档

启动服务后访问 http://localhost:8000/docs 查看 API 文档。

## 开发

```bash
# 运行测试
uv run pytest

# 代码格式化
uv run black .
uv run ruff check .
```

## 许可证

MIT
