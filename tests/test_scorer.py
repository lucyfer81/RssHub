import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.scorer import Scorer


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
async def test_score_item():
    """测试评分功能"""
    scorer = Scorer()

    mock_client = _make_mock_client({
        "choices": [{"message": {"content": "85.0"}}]
    })

    with patch("httpx.AsyncClient", return_value=mock_client):
        score = await scorer.score(
            title="AI 的未来",
            summary="讨论人工智能的发展趋势",
            user_preferences="喜欢: AI, 机器学习; 不喜欢: 政治"
        )

    assert 0 <= score <= 100
    assert score == 85.0


@pytest.mark.asyncio
async def test_score_item_invalid_response():
    """测试评分返回非数字时的默认值"""
    scorer = Scorer()

    mock_client = _make_mock_client({
        "choices": [{"message": {"content": "无法评分"}}]
    })

    with patch("httpx.AsyncClient", return_value=mock_client):
        score = await scorer.score(title="测试", summary="内容")

    assert score == 50.0  # 默认分数
