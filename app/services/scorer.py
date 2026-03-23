import httpx
import re
from app.config import get_settings

class Scorer:
    def __init__(self):
        settings = get_settings()
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def score(self, title: str, summary: str, user_preferences: str = "") -> float:
        """基于用户偏好对文章进行评分 (0-100)"""
        prompt = f"""请根据用户偏好对文章进行评分。

用户偏好:
{user_preferences}

文章:
标题: {title}
摘要: {summary}

请给出 0-100 的评分，只返回数字，不要解释。评分标准：
- 非常符合用户兴趣: 80-100
- 比较符合: 60-79
- 一般: 40-59
- 不太符合: 20-39
- 完全不符合: 0-19
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
                        "temperature": 0.3,
                    },
                )
                response.raise_for_status()
                result = response.json()

                score_text = result["choices"][0]["message"]["content"].strip()
                # 提取数字
                match = re.search(r'\d+', score_text)
                if match:
                    score = float(match.group())
                    return min(max(score, 0), 100)  # 限制在 0-100

                return 50.0  # 默认分数
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise RuntimeError(f"评分失败: {e}") from e
