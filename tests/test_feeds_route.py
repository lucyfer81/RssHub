import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_get_feeds():
    """测试获取所有 feeds"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/feeds")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_create_feed():
    """测试创建新 feed"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        feed_data = {
            "name": "测试 Feed",
            "url": "https://example.com/rss",
            "enabled": True
        }
        response = await client.post("/feeds", json=feed_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "测试 Feed"
        assert data["url"] == "https://example.com/rss"
        assert "id" in data

@pytest.mark.asyncio
async def test_sync_feed():
    """测试手动同步 feed"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 先创建一个 feed
        feed_data = {
            "name": "同步测试 Feed",
            "url": "https://example.com/rss",
            "enabled": True
        }
        create_response = await client.post("/feeds", json=feed_data)
        feed_id = create_response.json()["id"]

        # 测试同步
        response = await client.post(f"/feeds/{feed_id}/sync")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["feed_id"] == feed_id

@pytest.mark.asyncio
async def test_update_feed():
    """测试更新 feed"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 先创建一个 feed
        feed_data = {
            "name": "更新测试 Feed",
            "url": "https://example.com/rss",
            "enabled": True
        }
        create_response = await client.post("/feeds", json=feed_data)
        feed_id = create_response.json()["id"]

        # 更新 feed
        update_data = {
            "name": "已更新的 Feed",
            "url": "https://example.com/updated",
            "enabled": False
        }
        response = await client.patch(f"/feeds/{feed_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "已更新的 Feed"
        assert data["url"] == "https://example.com/updated"
        assert data["enabled"] == False

@pytest.mark.asyncio
async def test_delete_feed():
    """测试删除 feed"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 先创建一个 feed
        feed_data = {
            "name": "删除测试 Feed",
            "url": "https://example.com/rss",
            "enabled": True
        }
        create_response = await client.post("/feeds", json=feed_data)
        feed_id = create_response.json()["id"]

        # 删除 feed
        response = await client.delete(f"/feeds/{feed_id}")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["feed_id"] == feed_id
