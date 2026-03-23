import feedparser
import httpx
from hashlib import md5
from typing import List, Dict
from datetime import datetime
from app.config import get_settings

settings = get_settings()

class RSSFetcher:
    def __init__(self):
        self.timeout = settings.fetch_timeout

    async def fetch(self, url: str) -> List[Dict]:
        """抓取 RSS 源，返回文章列表"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            feed = feedparser.parse(response.content)

        items = []
        for entry in feed.entries[:settings.max_items_per_feed]:
            # 生成去重 key
            dedupe_key = md5(entry.get('link', '').encode()).hexdigest()

            items.append({
                "title": entry.get('title', ''),
                "link": entry.get('link', ''),
                "summary": entry.get('summary', ''),
                "published_at": self._parse_date(entry.get('published')),
                "dedupe_key": dedupe_key,
            })

        return items

    def _parse_date(self, date_str: str) -> datetime:
        """解析日期"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        except:
            return None
