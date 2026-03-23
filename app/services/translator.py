import httpx
from app.config import get_settings

settings = get_settings()


class Translator:
    def __init__(self):
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def translate(self, text: str, target_lang: str = "中文") -> str:
        """翻译文本到目标语言"""
        prompt = f"请将以下文本翻译成{target_lang}，只返回翻译结果，不要解释：\n\n{text}"

        async with httpx.AsyncClient() as client:
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
            return result["choices"][0]["message"]["content"].strip()
