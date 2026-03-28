import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.summarizer import Summarizer


def _make_mock_client(response_data: dict):
    """创建 mock httpx client"""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = response_data

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_summarize():
    """测试基本总结功能"""
    summarizer = Summarizer()

    mock_client = _make_mock_client({
        "choices": [{"message": {"content": "这是一篇关于人工智能的文章摘要。"}}]
    })

    with patch("httpx.AsyncClient", return_value=mock_client):
        summary = await summarizer.summarize("人工智能是计算机科学的一个分支。")

    assert len(summary) > 0
    assert isinstance(summary, str)


@pytest.mark.asyncio
async def test_summarize_empty_content():
    """测试空内容验证"""
    summarizer = Summarizer()
    with pytest.raises(ValueError, match="content 不能为空"):
        await summarizer.summarize("")


@pytest.mark.asyncio
async def test_summarize_long_content():
    """测试长内容截断"""
    summarizer = Summarizer()

    mock_client = _make_mock_client({
        "choices": [{"message": {"content": "长文章摘要。"}}]
    })

    long_content = "这是一段测试内容。" * 1000
    with patch("httpx.AsyncClient", return_value=mock_client):
        summary = await summarizer.summarize(long_content)

    assert len(summary) > 0
