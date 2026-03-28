import re
import logging
from app.services.content_fetcher import ContentFetcher
from app.services.translator import Translator, is_chinese
from app.services.summarizer import Summarizer

logger = logging.getLogger(__name__)


class ReadingPipeline:
    """阅读 pipeline：全文抓取 → 翻译 → 摘要 → 关键要点 → 阅读时长"""

    def __init__(self):
        self.fetcher = ContentFetcher()
        self.translator = Translator()
        self.summarizer = Summarizer()

    async def process(self, url: str, title: str, summary: str) -> dict:
        """执行完整的阅读处理 pipeline

        Args:
            url: 文章 URL
            title: 文章标题
            summary: 文章摘要

        Returns:
            dict: 处理结果，包含 content, content_zh, summary_ai, key_points, read_time_minutes
        """
        result = {
            "content": None,
            "content_zh": None,
            "summary_ai": None,
            "key_points": None,
            "read_time_minutes": None,
        }

        # 1. 抓取全文
        try:
            content = await self.fetcher.fetch(url)
            result["content"] = content if content else None
        except Exception as e:
            logger.warning(f"全文抓取失败 [{url}]: {e}")

        if not result["content"]:
            return result

        # 2. 翻译（非中文内容）
        try:
            if not is_chinese(result["content"]):
                result["content_zh"] = await self.translator.translate(result["content"][:4000])
            else:
                result["content_zh"] = None
        except Exception as e:
            logger.warning(f"全文翻译失败 [{url}]: {e}")

        # 3. 生成 AI 摘要
        try:
            text_for_summary = result["content_zh"] or result["content"]
            if text_for_summary:
                result["summary_ai"] = await self.summarizer.summarize(text_for_summary[:4000])
        except Exception as e:
            logger.warning(f"AI 摘要失败 [{url}]: {e}")

        # 4. 提取关键要点
        try:
            text_for_points = result["content_zh"] or result["content"]
            if text_for_points:
                result["key_points"] = await self.extract_key_points(text_for_points[:4000])
        except Exception as e:
            logger.warning(f"关键要点提取失败 [{url}]: {e}")

        # 5. 阅读时长估算
        text_for_time = result["content_zh"] or result["content"]
        if text_for_time:
            result["read_time_minutes"] = self.estimate_read_time(text_for_time)

        return result

    async def extract_key_points(self, content: str) -> list[str]:
        """使用 LLM 提取文章关键要点"""
        import httpx
        from app.config import get_settings

        settings = get_settings()

        prompt = f"""请从以下文章中提取 3-5 个最关键的要点。每个要点用一句话概括。
直接返回要点列表，每行一个要点，不要编号，不要其他内容。

文章内容：
{content}
"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            result = response.json()
            text = result["choices"][0]["message"]["content"].strip()

            points = [line.strip().lstrip("-•* ") for line in text.split("\n") if line.strip()]
            return [p for p in points if p][:5]

    def estimate_read_time(self, text: str) -> int:
        """估算阅读时长（分钟）

        中文：约 400 字/分钟
        英文：约 250 词/分钟
        """
        if not text:
            return 0

        if is_chinese(text):
            char_count = len(re.findall(r'[\u4e00-\u9fff]', text))
            return max(1, round(char_count / 400))
        else:
            word_count = len(text.split())
            return max(1, round(word_count / 250))
