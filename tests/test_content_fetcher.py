import pytest
import time
from unittest.mock import AsyncMock, patch
from app.services.content_fetcher import ContentFetcher


@pytest.mark.asyncio
async def test_fetch_full_content():
    """测试使用 requests 抓取全文内容"""
    fetcher = ContentFetcher()
    # 使用 example.com 进行简单测试
    content = await fetcher.fetch("https://example.com")
    assert len(content) > 0
    assert isinstance(content, str)


@pytest.mark.asyncio
async def test_rate_limit():
    """测试 Jina.ai 频率控制机制"""
    fetcher = ContentFetcher()
    fetcher.jina_rate_limit = 0.5  # 缩短测试时间

    start = time.time()
    await fetcher._rate_limit()  # 第一次，无等待
    await fetcher._rate_limit()  # 第二次，需要等待 jina_rate_limit 秒
    elapsed = time.time() - start

    assert elapsed >= fetcher.jina_rate_limit - 0.05  # 允许微小误差
