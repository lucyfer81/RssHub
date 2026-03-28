import pytest
from unittest.mock import AsyncMock, patch
from app.services.reading_pipeline import ReadingPipeline


@pytest.mark.asyncio
async def test_pipeline_calls_content_fetcher():
    """测试 pipeline 调用 content_fetcher"""
    pipeline = ReadingPipeline()
    pipeline.fetcher = AsyncMock()
    pipeline.fetcher.fetch.return_value = "full article content"
    pipeline.translator = AsyncMock()
    pipeline.translator.translate.return_value = "翻译后的内容"
    pipeline.summarizer = AsyncMock()
    pipeline.summarizer.summarize.return_value = "AI 摘要"

    with patch.object(pipeline, 'extract_key_points', new_callable=AsyncMock) as mock_kp:
        mock_kp.return_value = ["要点1", "要点2"]
        result = await pipeline.process("https://example.com/article", "Article Title", "")

    assert result["content"] == "full article content"
    assert result["content_zh"] == "翻译后的内容"
    assert result["summary_ai"] == "AI 摘要"
    assert result["key_points"] == ["要点1", "要点2"]
    assert result["read_time_minutes"] > 0
    pipeline.fetcher.fetch.assert_called_once_with("https://example.com/article")


@pytest.mark.asyncio
async def test_pipeline_continues_on_fetch_failure():
    """测试抓取失败时 pipeline 不崩溃"""
    pipeline = ReadingPipeline()
    pipeline.fetcher = AsyncMock()
    pipeline.fetcher.fetch.return_value = ""
    pipeline.translator = AsyncMock()
    pipeline.summarizer = AsyncMock()

    result = await pipeline.process("https://example.com/fail", "Title", "summary")

    assert result["content"] is None
    assert result["content_zh"] is None
    assert result["summary_ai"] is None


@pytest.mark.asyncio
async def test_pipeline_skips_translation_for_chinese():
    """测试中文内容跳过翻译"""
    pipeline = ReadingPipeline()
    pipeline.fetcher = AsyncMock()
    pipeline.fetcher.fetch.return_value = "这是一篇中文文章内容" * 50
    pipeline.translator = AsyncMock()
    pipeline.summarizer = AsyncMock()
    pipeline.summarizer.summarize.return_value = "摘要"

    with patch.object(pipeline, 'extract_key_points', new_callable=AsyncMock) as mock_kp:
        mock_kp.return_value = ["要点"]
        result = await pipeline.process("https://example.com/cn", "中文标题", "中文摘要")

    pipeline.translator.translate.assert_not_called()
    assert result["content_zh"] is None


def test_estimate_read_time_chinese():
    """测试中文阅读时长估算"""
    pipeline = ReadingPipeline()
    # 400字/分钟，800字 = 2分钟
    minutes = pipeline.estimate_read_time("这是一段中文测试文本" * 100)
    assert minutes == 2


def test_estimate_read_time_english():
    """测试英文阅读时长估算"""
    pipeline = ReadingPipeline()
    # 250词/分钟，250词 = 1分钟
    text = " ".join(["word"] * 250)
    minutes = pipeline.estimate_read_time(text)
    assert minutes == 1


def test_estimate_read_time_empty():
    """测试空文本返回 0"""
    pipeline = ReadingPipeline()
    assert pipeline.estimate_read_time("") == 0
    assert pipeline.estimate_read_time(None) == 0
