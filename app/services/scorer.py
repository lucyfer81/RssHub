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
        # 输入验证
        if not title or not title.strip():
            raise ValueError("title 不能为空")

        if not summary or not summary.strip():
            raise ValueError("summary 不能为空")

        # 构建用户偏好描述
        preferences_text = user_preferences if user_preferences.strip() else "AI/LLM、编程开发、技术深度文章"

        prompt = f"""你是一个内容推荐评分助手。请根据用户偏好和文章内容，给出 0-100 的精准评分。

## 用户偏好
{preferences_text}

## 待评分文章
标题: {title}
摘要: {summary}

## 评分标准（必须严格执行）
1. **主题相关性 (40分)**
   - 直接涉及 AI/LLM/编程: 35-40分
   - 技术相关但非核心: 20-34分
   - 非技术内容: 0-19分

2. **内容深度 (30分)**
   - 深度技术分析/原创研究: 25-30分
   - 有见解的评论/教程: 15-24分
   - 轻资讯/转载: 5-14分
   - 纯营销/标题党: 0-4分

3. **时效性与新颖性 (20分)**
   - 最新突破/公告: 15-20分
   - 行业趋势分析: 8-14分
   - 陈旧内容: 0-7分

4. **可读性 (10分)**
   - 清晰易懂有结构: 8-10分
   - 一般可读: 4-7分
   - 晦涩难懂: 0-3分

## 评分示例

示例1:
标题: "GPT-4 solves International Mathematics Olympiad problem"
摘要: "OpenAI announces GPT-4 has achieved a breakthrough in mathematical reasoning..."
评分: 95.0

示例2:
标题: "10 tips for better productivity"
摘要: "Generic advice about being productive at work..."
评分: 25.0

示例3:
标题: "Fashion trends for spring 2024"
摘要: "The latest fashion styles for the upcoming season..."
评分: 5.0

## 输出要求
只输出一个 0-100 之间的数字（保留1位小数），不要任何其他内容。
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
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()
                result = response.json()

                # 验证响应结构
                if "choices" not in result or not result["choices"]:
                    raise ValueError("API 响应缺少 choices 字段")

                score_text = result["choices"][0]["message"]["content"].strip()
                # 匹配 0-100 的数字（可选小数）
                match = re.search(r'\b(100(?:\.0+)?|[1-9]?\d(?:\.\d+)?)\b', score_text)
                if match:
                    score = float(match.group())
                    return min(max(score, 0), 100)  # 限制在 0-100

                return 50.0  # 默认分数
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise RuntimeError(f"评分失败: {e}") from e

    async def score_full(self, title: str, content: str, user_preferences: str = "") -> float:
        """基于标题+全文内容对文章进行评分 (0-100)"""
        # 输入验证
        if not title or not title.strip():
            raise ValueError("title 不能为空")

        if not content or not content.strip():
            raise ValueError("content 不能为空")

        # 构建用户偏好描述
        preferences_text = user_preferences if user_preferences.strip() else "AI/LLM、编程开发、技术深度文章"

        # 截断正文到 4000 字符
        truncated = content[:4000]

        prompt = f"""你是一个内容推荐评分助手。请根据用户偏好和文章内容，给出 0-100 的精准评分。

## 用户偏好
{preferences_text}

## 待评分文章
标题: {title}
正文: {truncated}

## 评分标准（必须严格执行）
1. **主题相关性 (40分)**
   - 直接涉及 AI/LLM/编程: 35-40分
   - 技术相关但非核心: 20-34分
   - 非技术内容: 0-19分

2. **内容深度 (30分)**
   - 深度技术分析/原创研究: 25-30分
   - 有见解的评论/教程: 15-24分
   - 轻资讯/转载: 5-14分
   - 纯营销/标题党: 0-4分

3. **时效性与新颖性 (20分)**
   - 最新突破/公告: 15-20分
   - 行业趋势分析: 8-14分
   - 陈旧内容: 0-7分

4. **可读性 (10分)**
   - 清晰易懂有结构: 8-10分
   - 一般可读: 4-7分
   - 晦涩难懂: 0-3分

## 评分示例

示例1:
标题: "GPT-4 solves International Mathematics Olympiad problem"
正文: "OpenAI announces GPT-4 has achieved a breakthrough in mathematical reasoning..."
评分: 95.0

示例2:
标题: "10 tips for better productivity"
正文: "Generic advice about being productive at work..."
评分: 25.0

示例3:
标题: "Fashion trends for spring 2024"
正文: "The latest fashion styles for the upcoming season..."
评分: 5.0

## 输出要求
只输出一个 0-100 之间的数字（保留1位小数），不要任何其他内容。
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
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()
                result = response.json()

                # 验证响应结构
                if "choices" not in result or not result["choices"]:
                    raise ValueError("API 响应缺少 choices 字段")

                score_text = result["choices"][0]["message"]["content"].strip()
                # 匹配 0-100 的数字（可选小数）
                match = re.search(r'\b(100(?:\.0+)?|[1-9]?\d(?:\.\d+)?)\b', score_text)
                if match:
                    score = float(match.group())
                    return min(max(score, 0), 100)  # 限制在 0-100

                return 50.0  # 默认分数
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise RuntimeError(f"评分失败: {e}") from e
