import jieba
from collections import Counter
from typing import List
from app.config import get_settings

settings = get_settings()

class PreferenceService:
    def __init__(self):
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    async def extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 输入验证
        if not text or not text.strip():
            return []

        # 使用 jieba 分词
        words = jieba.cut(text)
        # 过滤停用词和短词
        keywords = [w for w in words if len(w) >= 2]
        # 返回前 10 个高频词
        counter = Counter(keywords)
        return [word for word, _ in counter.most_common(10)]

    async def get_user_preferences(self, db_session) -> str:
        """聚合用户偏好为提示词"""
        # 这里简化实现，实际应该从 preferences 表聚合
        return "喜欢: AI, 技术, 编程; 不喜欢: 政治, 娱乐"

    async def learn_from_feedback(self, item_id: int, feedback: str, score_diff: float = None):
        """从用户反馈中学习"""
        # 这里简化，实际应该存储到 preferences 表
        pass
