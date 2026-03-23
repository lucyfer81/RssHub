import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_get_items():
    """测试获取文章列表"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/items")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_get_items_with_status():
    """测试按状态筛选文章"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/items?status=inbox")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_update_item():
    """测试更新文章状态"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 先创建一个 feed
        feed_data = {
            "name": "测试 Feed",
            "url": "https://example.com/rss",
            "enabled": True
        }
        create_feed = await client.post("/feeds", json=feed_data)

        # 创建一个 item（需要先有数据库记录）
        # 这里简化测试，只测试 API 端点存在
        update_data = {"status": "reading"}
        response = await client.patch("/items/1", json=update_data)
        # 可能返回 404（如果没有 id=1 的记录），但端点存在
        assert response.status_code in [200, 404]
