import pytest
from app.services.summarizer import Summarizer


@pytest.mark.asyncio
async def test_summarize():
    """测试基本总结功能"""
    summarizer = Summarizer()
    content = """
    人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，
    它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。
    该领域的研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。
    人工智能从诞生以来，理论和技术日益成熟，应用领域也不断扩大。
    """
    summary = await summarizer.summarize(content)
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
    # 创建超过 4000 字符的内容
    long_content = "这是一段测试内容。" * 1000
    summary = await summarizer.summarize(long_content)
    assert len(summary) > 0
