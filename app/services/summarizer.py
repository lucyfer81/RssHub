import httpx
from app.config import get_settings


class Summarizer:
    def __init__(self):
        settings = get_settings()
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def summarize(self, content: str, lang: str = "中文") -> str:
        """生成文章摘要"""
        # 输入验证
        if not content or not content.strip():
            raise ValueError("content 不能为空")

        if not lang or not lang.strip():
            raise ValueError("lang 不能为空")

        # 限制输入长度，避免超过 API 限制
        truncated_content = content[:4000] if len(content) > 4000 else content

        prompt = f"""请用{lang}为以下文章写一个简洁的摘要（200字以内）：

{truncated_content}
"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.5,
                    },
                )
                response.raise_for_status()
                result = response.json()

                # 验证响应结构
                if "choices" not in result or not result["choices"]:
                    raise ValueError("API 响应缺少 choices 字段")

                if "message" not in result["choices"][0]:
                    raise ValueError("API 响应缺少 message 字段")

                if "content" not in result["choices"][0]["message"]:
                    raise ValueError("API 响应缺少 content 字段")

                return result["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise RuntimeError(f"总结失败: {e}") from e
