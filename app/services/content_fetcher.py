import httpx
import asyncio
import time
from typing import Optional
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from app.config import get_settings

settings = get_settings()


class ContentFetcher:
    """多级回退策略抓取全文内容
    1. requests + BeautifulSoup (最快，静态页面)
    2. playwright (JS渲染页面)
    3. Jina.ai (保底)
    """

    def __init__(self):
        self.jina_rate_limit = settings.jina_rate_limit_seconds
        self._last_jina_fetch = 0
        self._lock = asyncio.Lock()
        self._session: Optional[httpx.AsyncClient] = None

    async def _get_session(self) -> httpx.AsyncClient:
        """获取复用的 httpx session"""
        if self._session is None:
            self._session = httpx.AsyncClient(timeout=30, follow_redirects=True)
        return self._session

    async def close(self):
        """关闭 session"""
        if self._session:
            await self._session.aclose()

    async def fetch(self, url: str) -> str:
        """使用多级回退策略抓取全文

        Args:
            url: 要抓取的网页 URL

        Returns:
            抓取的文本内容，如果全部失败返回空字符串
        """
        print(f"  抓取正文: {url[:60]}...")

        # 1. 尝试 requests + BeautifulSoup
        content = await self._fetch_with_requests(url)
        if content:
            print(f"    ✓ Requests 成功 ({len(content)} 字符)")
            return content

        # 2. 尝试 playwright
        content = await self._fetch_with_playwright(url)
        if content:
            print(f"    ✓ Playwright 成功 ({len(content)} 字符)")
            return content

        # 3. 保底：Jina.ai
        content = await self._fetch_with_jina(url)
        if content:
            print(f"    ✓ Jina.ai 成功 ({len(content)} 字符)")
            return content

        print(f"    ✗ 全部失败")
        return ""

    async def _fetch_with_requests(self, url: str) -> Optional[str]:
        """使用 requests + BeautifulSoup 抓取静态页面"""
        try:
            session = await self._get_session()
            response = await session.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # 移除不需要的标签
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
                tag.decompose()

            # 尝试找到主要内容区域
            content = None

            # 常见的内容选择器
            selectors = [
                "article",
                "[role='main']",
                "main",
                ".post-content",
                ".entry-content",
                ".article-content",
                ".content",
                "#content",
                ".post-body",
                ".article-body",
            ]

            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    content = element.get_text(separator="\n", strip=True)
                    if len(content) > 200:  # 确保内容足够长
                        break

            # 如果没找到特定区域，使用 body
            if not content or len(content) < 200:
                body = soup.find("body")
                if body:
                    content = body.get_text(separator="\n", strip=True)

            if content and len(content) > 100:
                # 清理多余空白
                lines = [line.strip() for line in content.split("\n") if line.strip()]
                return "\n".join(lines)

            return None

        except Exception as e:
            return None

    async def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """使用 playwright 抓取 JS 渲染页面"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = await context.new_page()

                await page.goto(url, wait_until="domcontentloaded", timeout=15000)

                # 等待内容加载
                await asyncio.sleep(1)

                content = await page.evaluate("""() => {
                    // 移除不需要的元素
                    const selectors = ['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', '.sidebar', '.navigation'];
                    selectors.forEach(s => {
                        document.querySelectorAll(s).forEach(el => el.remove());
                    });

                    // 尝试找到主内容
                    const contentSelectors = [
                        'article',
                        '[role="main"]',
                        'main',
                        '.post-content',
                        '.entry-content',
                        '.article-content',
                        '.content',
                        '#content',
                        '.post-body',
                        '.article-body',
                    ];

                    for (const selector of contentSelectors) {
                        const el = document.querySelector(selector);
                        if (el && el.textContent.length > 200) {
                            return el.textContent;
                        }
                    }

                    // 保底使用 body
                    return document.body.textContent;
                }""")

                await browser.close()

                if content:
                    # 清理空白
                    lines = [line.strip() for line in content.split("\n") if line.strip()]
                    content = "\n".join(lines)
                    if len(content) > 100:
                        return content

                return None

        except (PlaywrightTimeout, Exception) as e:
            return None

    async def _fetch_with_jina(self, url: str) -> Optional[str]:
        """使用 Jina.ai Reader API 作为保底方案"""
        # 频率控制
        await self._rate_limit()

        try:
            session = await self._get_session()
            jina_url = f"https://r.jina.ai/{url}"
            response = await session.get(jina_url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return None

    async def _rate_limit(self):
        """Jina.ai 频率控制"""
        async with self._lock:
            if self._last_jina_fetch:
                elapsed = time.monotonic() - self._last_jina_fetch
                if elapsed < self.jina_rate_limit:
                    await asyncio.sleep(self.jina_rate_limit - elapsed)
            self._last_jina_fetch = time.monotonic()
