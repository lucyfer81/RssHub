import pytest
from app.services.preference import PreferenceService

@pytest.mark.asyncio
async def test_extract_keywords():
    service = PreferenceService()
    keywords = await service.extract_keywords("这是一篇关于人工智能和机器学习的文章")
    assert "人工智能" in keywords or "机器学习" in keywords

@pytest.mark.asyncio
async def test_extract_keywords_empty_input():
    service = PreferenceService()
    keywords = await service.extract_keywords("")
    assert keywords == []

@pytest.mark.asyncio
async def test_extract_keywords_whitespace_only():
    service = PreferenceService()
    keywords = await service.extract_keywords("   ")
    assert keywords == []
