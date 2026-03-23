import pytest
from app.services.translator import Translator


@pytest.mark.asyncio
async def test_translate_text():
    translator = Translator()
    result = await translator.translate("Hello, world!", target_lang="中文")
    assert "你好" in result or "世界" in result
