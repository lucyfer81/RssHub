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

        frontmatter = {k: v for k, v in frontmatter.items() if v is not None}

        md_content = f"---\n{yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)}---\n\n{content}"
        file_path.write_text(md_content, encoding="utf-8")

        return f"{date_str}/{file_path.name}"
