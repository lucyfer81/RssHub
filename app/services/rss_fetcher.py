import feedparser
import httpx
import re
from hashlib import md5
from typing import List, Dict, Optional
from datetime import datetime
from markdownify import markdownify as md
from app.config import get_settings

settings = get_settings()


def clean_html_to_markdown(html: str) -> str:
    """将 HTML 转换为 Markdown 并清理多余空白

    Args:
        html: 原始 HTML 内容

    Returns:
        清理后的 Markdown 文本
    """
    if not html:
        return ""

    # 转换为 Markdown
    text = md(html, strip=['script', 'style'])

    # 清理多余空白
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text

class RSSFetcher:
    def __init__(self):
        self.timeout = settings.fetch_timeout

    async def fetch(self, url: str) -> List[Dict]:
        """抓取 RSS 源，返回文章列表"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
        except Exception as e:
            # 网络错误，返回空列表
            print(f"  抓取错误: {type(e).__name__}: {e}")
            return []

        # 验证 feed
        if not feed or not hasattr(feed, 'entries') or not feed.entries:
            return []

        items = []
        for entry in feed.entries[:settings.max_items_per_feed]:
            # 生成去重 key
            dedupe_key = md5(entry.get('link', '').encode()).hexdigest()

            items.append({
                "title": entry.get('title', ''),
                "link": entry.get('link', ''),
                "summary": clean_html_to_markdown(entry.get('summary', '')),
                "published_at": self._parse_date(entry.get('published')),
                "dedupe_key": dedupe_key,
            })

        return items

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析日期"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        except (ValueError, TypeError):
            return None
