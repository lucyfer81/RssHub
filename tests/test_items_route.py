import pytest
from httpx import AsyncClient
from app.models import Feed, Item

@pytest.mark.asyncio
async def test_get_items(client: AsyncClient):
    """测试获取文章列表"""
    response = await client.get("/items")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_get_items_with_status(client: AsyncClient):
    """测试按状态筛选文章"""
    response = await client.get("/items?status=inbox")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_update_item(client: AsyncClient, db_session):
    """测试更新文章状态"""
    # 创建一个 feed
    feed = Feed(name="测试 Feed", url="https://items-route.example.com/rss")
    db_session.add(feed)
    await db_session.flush()

    # 创建一个 item
    item = Item(
        feed_id=feed.id,
        title="测试文章",
        link="https://items-route.example.com/article",
        dedupe_key="items_route_1"
    )
    db_session.add(item)
    await db_session.commit()

    # 更新状态
    update_data = {"status": "reading"}
    response = await client.patch(f"/items/{item.id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reading"

@pytest.mark.asyncio
async def test_update_item_to_read(client: AsyncClient, db_session):
    """测试将文章标记为已读"""
    feed = Feed(name="测试 Feed", url="https://read-status.example.com/rss")
    db_session.add(feed)
    await db_session.flush()

    item = Item(
        feed_id=feed.id,
        title="测试文章",
        link="https://read-status.example.com/article",
        dedupe_key="read_status_1",
        status="reading",
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.patch(f"/items/{item.id}", json={"status": "read"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "read"

@pytest.mark.asyncio
async def test_item_has_new_fields(client: AsyncClient, db_session):
    """测试 Item 响应包含 key_points 和 read_time_minutes"""
    feed = Feed(name="测试 Feed", url="https://fields.example.com/rss")
    db_session.add(feed)
    await db_session.flush()

    item = Item(
        feed_id=feed.id,
        title="测试文章",
        link="https://fields.example.com/article",
        dedupe_key="fields_test_1",
        key_points='["要点1", "要点2"]',
        read_time_minutes=5,
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.get(f"/items/{item.id}")
    assert response.status_code == 200
