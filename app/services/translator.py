import httpx
import re
from app.config import get_settings


def is_chinese(text: str) -> bool:
    """检测文本是否主要是中文"""
    if not text:
        return False
    # 统计中文字符比例
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_chars = len(text.strip())
    if total_chars == 0:
        return False
    # 如果中文字符占比超过50%，认为是中文
    return chinese_chars / total_chars > 0.5


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

        # 如果目标语言是中文且文本已是中文，直接返回
        if target_lang == "中文" and is_chinese(text):
            return text

        prompt = f"请将以下文本翻译成{target_lang}。要求：只返回翻译结果，不要解释，不要使用HTML标签，保持原有的Markdown格式。\n\n{text}"

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
