import pytest
from app.services.rss_fetcher import RSSFetcher

@pytest.mark.asyncio
async def test_fetch_feed_items():
    fetcher = RSSFetcher()
    items = await fetcher.fetch("https://simonwillison.net/atom/everything/")
    assert len(items) > 0
    assert "title" in items[0]
    assert "link" in items[0]
