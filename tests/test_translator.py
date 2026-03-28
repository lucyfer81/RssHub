import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.translator import Translator, is_chinese


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


def test_is_chinese_with_chinese_text():
    assert is_chinese("这是一段中文文本") is True


def test_is_chinese_with_english_text():
    assert is_chinese("This is English text") is False


def test_is_chinese_with_empty_text():
    assert is_chinese("") is False


def test_is_chinese_with_mixed_text():
    assert is_chinese("hello world 你好") is False


@pytest.mark.asyncio
async def test_translate_text():
    """测试翻译功能"""
    translator = Translator()

    mock_client = _make_mock_client({
        "choices": [{"message": {"content": "你好世界"}}]
    })

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await translator.translate("Hello, world!", target_lang="中文")

    assert "你好" in result


@pytest.mark.asyncio
async def test_translate_skips_chinese():
    """测试中文文本跳过翻译"""
    translator = Translator()
    result = await translator.translate("这是一段中文文本", target_lang="中文")
    assert result == "这是一段中文文本"
