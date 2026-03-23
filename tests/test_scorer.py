import pytest
from app.services.scorer import Scorer

@pytest.mark.asyncio
async def test_score_item():
    scorer = Scorer()
    score = await scorer.score(
        title="AI 的未来",
        summary="讨论人工智能的发展趋势",
        user_preferences="喜欢: AI, 机器学习; 不喜欢: 政治"
    )
    assert 0 <= score <= 100
