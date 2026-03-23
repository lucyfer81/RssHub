import pytest
from app.services.content_fetcher import ContentFetcher


@pytest.mark.asyncio
async def test_fetch_full_content():
    """测试使用 Jina.ai 抓取全文内容"""
    fetcher = ContentFetcher()
    # 使用 example.com 进行简单测试
    content = await fetcher.fetch("https://example.com")
    assert len(content) > 0
    assert isinstance(content, str)


@pytest.mark.asyncio
async def test_rate_limit():
    """测试频率控制机制"""
    fetcher = ContentFetcher()
    # 连续请求两次，第二次应该受到频率限制
    import time
    start = time.time()
    await fetcher.fetch("https://example.com")
    await fetcher.fetch("https://example.com")
    elapsed = time.time() - start
    # 由于频率限制，至少应该消耗 rate_limit_seconds 的时间
    assert elapsed >= fetcher.rate_limit
