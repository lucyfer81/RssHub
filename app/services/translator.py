import httpx
from app.config import get_settings


class Translator:
    def __init__(self):
        settings = get_settings()
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def translate(self, text: str, target_lang: str = "中文") -> str:
        """翻译文本到目标语言"""
        # 输入验证
        if not text or not text.strip():
            raise ValueError("text 不能为空")

        if not target_lang or not target_lang.strip():
            raise ValueError("target_lang 不能为空")

        prompt = f"请将以下文本翻译成{target_lang}，只返回翻译结果，不要解释：\n\n{text}"

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
                        "temperature": 0.3,
                    },
                )
                response.raise_for_status()
                result = response.json()

                # 验证响应结构
                if "choices" not in result or not result["choices"]:
                    raise ValueError("API 响应缺少 choices 字段")

                return result["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise RuntimeError(f"翻译失败: {e}") from e
