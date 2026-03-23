import httpx
import asyncio
import time
from app.config import get_settings

settings = get_settings()


class ContentFetcher:
    """使用 Jina.ai Reader API 抓取全文内容"""

    def __init__(self):
        self.rate_limit = settings.jina_rate_limit_seconds
        self._last_fetch = 0
        self._lock = asyncio.Lock()

    async def fetch(self, url: str) -> str:
        """使用 Jina.ai Reader API 抓取全文

        Args:
            url: 要抓取的网页 URL

        Returns:
            抓取的文本内容

        Raises:
            httpx.HTTPError: 当请求失败时
        """
        # 频率控制
        await self._rate_limit()

        jina_url = f"https://r.jina.ai/{url}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(jina_url)
            response.raise_for_status()
            return response.text

    async def _rate_limit(self):
        """简单的频率控制（线程安全）"""
        async with self._lock:
            if self._last_fetch:
                elapsed = time.monotonic() - self._last_fetch
                if elapsed < self.rate_limit:
                    await asyncio.sleep(self.rate_limit - elapsed)
            self._last_fetch = time.monotonic()
