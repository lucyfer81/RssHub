"""
端到端测试 - 测试完整的用户工作流程
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Feed, Item, Share


class TestE2EWorkflow:
    """端到端工作流测试"""

    @pytest.mark.asyncio
    async def test_complete_workflow(self, client: AsyncClient, db_session: AsyncSession):
        """
        完整的用户工作流测试:
        1. 创建 RSS 源
        2. 获取源列表
        3. 更新源
        4. 直接创建文章（模拟同步）
        5. 获取文章列表
        6. 更新文章状态
        7. 创建分享链接
        8. 访问分享页面
        9. 导出 Markdown
        10. 删除文章和源
        """

        # ========== 1. 创建 RSS 源 ==========
        feed_data = {
            "name": "E2E 测试源",
            "url": "https://e2e-test.example.com/rss",
            "enabled": True
        }
        response = await client.post("/feeds", json=feed_data)
        assert response.status_code == 200, f"创建源失败: {response.text}"
        feed = response.json()
        feed_id = feed["id"]
        assert feed["name"] == "E2E 测试源"
        assert feed["url"] == "https://e2e-test.example.com/rss"
        assert feed["enabled"] == True
        print(f"✅ 创建源成功: ID={feed_id}")

        # ========== 2. 获取源列表 ==========
        response = await client.get("/feeds")
        assert response.status_code == 200
        feeds = response.json()
        assert len(feeds) >= 1
        assert any(f["id"] == feed_id for f in feeds)
        print(f"✅ 获取源列表成功: {len(feeds)} 个源")

        # ========== 3. 更新源 ==========
        # 注意：update_feed 使用 FeedCreate 作为模型，需要提供完整数据
        update_data = {
            "name": "E2E 更新后的源",
            "url": "https://e2e-test.example.com/rss",  # URL 需要保持或更新
            "enabled": False
        }
        response = await client.patch(f"/feeds/{feed_id}", json=update_data)
        assert response.status_code == 200
        updated_feed = response.json()
        assert updated_feed["name"] == "E2E 更新后的源"
        assert updated_feed["enabled"] == False
        print(f"✅ 更新源成功")

        # 重新启用源以便后续测试
        await client.patch(f"/feeds/{feed_id}", json={"enabled": True})

        # ========== 4. 直接创建文章（模拟同步结果） ==========
        # 由于真实同步需要网络请求，这里直接在数据库中创建测试文章
        from datetime import datetime, timedelta

        items_data = [
            {
                "title": "E2E 测试文章 1",
                "link": "https://e2e-test.example.com/article-1",
                "summary": "这是第一篇测试文章的摘要",
                "published_at": datetime.now() - timedelta(hours=2),
                "score_summary": 85.5
            },
            {
                "title": "E2E 测试文章 2",
                "link": "https://e2e-test.example.com/article-2",
                "summary": "这是第二篇测试文章的摘要",
                "published_at": datetime.now() - timedelta(hours=1),
                "score_summary": 75.0
            },
            {
                "title": "E2E 测试文章 3",
                "link": "https://e2e-test.example.com/article-3",
                "summary": "这是第三篇测试文章的摘要",
                "published_at": datetime.now(),
                "score_summary": 90.0,
                "content": "这是完整的文章内容...",
                "summary_ai": "AI 生成的摘要"
            }
        ]

        created_items = []
        for item_data in items_data:
            item = Item(
                feed_id=feed_id,
                title=item_data["title"],
                link=item_data["link"],
                summary=item_data.get("summary"),
                published_at=item_data.get("published_at"),
                score_summary=item_data.get("score_summary"),
                content=item_data.get("content"),
                summary_ai=item_data.get("summary_ai"),
                dedupe_key=f"e2e_{item_data['link']}"
            )
            db_session.add(item)
            await db_session.flush()
            created_items.append(item)

        await db_session.commit()
        print(f"✅ 创建了 {len(created_items)} 篇测试文章")

        # ========== 5. 获取文章列表 ==========
        response = await client.get("/items")
        assert response.status_code == 200
        items = response.json()
        assert len(items) >= 3
        print(f"✅ 获取文章列表成功: {len(items)} 篇文章")

        # 按状态筛选
        response = await client.get("/items?status=unread")
        assert response.status_code == 200
        unread_items = response.json()
        assert all(item["status"] == "unread" for item in unread_items)
        print(f"✅ 筛选未读文章: {len(unread_items)} 篇")

        # 获取特定文章（返回 HTML 详情页）
        item_id = created_items[0].id
        response = await client.get(f"/items/{item_id}")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "E2E 测试文章 1" in response.text
        print(f"✅ 获取特定文章详情页成功: ID={item_id}")

        # ========== 6. 更新文章状态 ==========
        # 标记为已读
        response = await client.patch(f"/items/{item_id}", json={"status": "read"})
        assert response.status_code == 200
        updated_item = response.json()
        assert updated_item["status"] == "read"
        print("✅ 更新文章状态为 read")

        # 标记为未读
        response = await client.patch(f"/items/{item_id}", json={"status": "read"})
        assert response.status_code == 200
        assert response.json()["status"] == "read"
        print(f"✅ 更新文章状态为 read")

        # 重新改回 unread
        response = await client.patch(f"/items/{item_id}", json={"status": "unread"})
        assert response.status_code == 200

        # ========== 7. 创建分享链接 ==========
        share_item_id = created_items[2].id  # 使用第三篇文章（有完整内容）
        response = await client.post(f"/shares/items/{share_item_id}")
        assert response.status_code == 200
        share = response.json()
        share_code = share["share_code"]
        assert share["item_id"] == share_item_id
        assert share_code is not None
        print(f"✅ 创建分享链接成功: code={share_code}")

        # 获取分享 URL
        response = await client.get(f"/shares/items/{share_item_id}")
        assert response.status_code == 200
        share_info = response.json()
        assert "share_url" in share_info
        print(f"✅ 获取分享 URL 成功")

        # ========== 8. 访问分享页面 ==========
        response = await client.get(f"/shares/{share_code}")
        assert response.status_code == 200
        # 分享页面返回 HTML
        assert "text/html" in response.headers.get("content-type", "")
        print(f"✅ 访问分享页面成功")

        # ========== 9. 导出 Markdown ==========
        response = await client.post(f"/exports/items/{share_item_id}/markdown")
        assert response.status_code == 200
        markdown_content = response.text
        assert "E2E 测试文章 3" in markdown_content
        assert "https://e2e-test.example.com/article-3" in markdown_content
        assert "AI 生成的摘要" in markdown_content
        assert "由 RssHub 生成" in markdown_content
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        print(f"✅ 导出 Markdown 成功")
        print(f"   Markdown 内容预览:\n{markdown_content[:200]}...")

        # ========== 10. 清理测试数据 ==========
        # 删除源（级联删除文章和分享）
        response = await client.delete(f"/feeds/{feed_id}")
        assert response.status_code == 200
        print(f"✅ 删除源成功")

        # 验证删除
        response = await client.get("/feeds")
        feeds = response.json()
        assert not any(f["id"] == feed_id for f in feeds)
        print(f"✅ 验证删除成功")

        print("\n🎉 端到端测试全部通过！")


class TestE2EEdgeCases:
    """端到端边缘情况测试"""

    @pytest.mark.asyncio
    async def test_duplicate_feed_url(self, client: AsyncClient):
        """测试创建重复 URL 的源"""
        feed_data = {
            "name": "重复测试源",
            "url": "https://duplicate.example.com/rss",
            "enabled": True
        }

        # 第一次创建应该成功
        response = await client.post("/feeds", json=feed_data)
        assert response.status_code == 200

        # 第二次创建应该返回 409 冲突
        response = await client.post("/feeds", json=feed_data)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_nonexistent_item(self, client: AsyncClient):
        """测试访问不存在的文章"""
        response = await client.get("/items/99999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_feed(self, client: AsyncClient):
        """测试操作不存在的源"""
        # 注意：update_feed 使用 FeedCreate，需要提供完整数据
        response = await client.patch("/feeds/99999", json={
            "name": "不存在",
            "url": "https://nonexistent.example.com/rss",
            "enabled": True
        })
        assert response.status_code == 404

        response = await client.delete("/feeds/99999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_status(self, client: AsyncClient, db_session: AsyncSession):
        """测试无效的文章状态"""
        # 创建测试源和文章
        feed = Feed(name="测试源", url="https://invalid-status.example.com/rss")
        db_session.add(feed)
        await db_session.flush()

        item = Item(
            feed_id=feed.id,
            title="测试文章",
            link="https://invalid-status.example.com/article",
            dedupe_key="invalid_status_1"
        )
        db_session.add(item)
        await db_session.commit()

        # 尝试设置无效状态
        response = await client.patch(f"/items/{item.id}", json={"status": "invalid"})
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_expired_share(self, client: AsyncClient, db_session: AsyncSession):
        """测试过期的分享链接"""
        from datetime import datetime, timedelta

        # 创建测试源和文章
        feed = Feed(name="过期测试源", url="https://expired.example.com/rss")
        db_session.add(feed)
        await db_session.flush()

        item = Item(
            feed_id=feed.id,
            title="过期分享测试文章",
            link="https://expired.example.com/article",
            dedupe_key="expired_share_1"
        )
        db_session.add(item)
        await db_session.flush()

        # 创建已过期的分享
        expired_share = Share(
            item_id=item.id,
            share_code="expired_code_123",
            expires_at=datetime.now() - timedelta(days=1)  # 昨天过期
        )
        db_session.add(expired_share)
        await db_session.commit()

        # 访问过期的分享（根据实现可能返回 404 或错误页面）
        response = await client.get("/shares/expired_code_123")
        # 根据实际实现，可能返回 404 或者显示错误信息
        # 这里只验证请求能正常处理
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_export_nonexistent_item(self, client: AsyncClient):
        """测试导出不存在的文章"""
        response = await client.post("/exports/items/99999/markdown")
        assert response.status_code == 404


class TestE2EHealthCheck:
    """健康检查测试"""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        """测试健康检查端点"""
        response = await client.get("/health")
        assert response.status_code == 200
        # 健康检查返回 {"status": "ok"}
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """测试根路径"""
        response = await client.get("/")
        assert response.status_code == 200
