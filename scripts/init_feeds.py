#!/usr/bin/env python
"""
初始化 RSS 源数据

运行此脚本将预设的 RSS 源添加到数据库中。
"""
import asyncio
from app.database import async_session
from app.models import Feed

# 初始 RSS 源列表
INITIAL_FEEDS = [
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"},
    {"name": "Hacker News Frontpage", "url": "https://hnrss.org/frontpage"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed"},
    {"name": "Andrej Karpathy", "url": "https://karpathy.bearblog.dev/feed/"},
    {"name": "Sebastian Raschka", "url": "https://magazine.sebastianraschka.com/feed"},
]


async def init():
    """初始化 RSS 源"""
    async with async_session() as session:
        for feed_data in INITIAL_FEEDS:
            # 检查是否已存在
            from sqlalchemy import select
            result = await session.execute(
                select(Feed).where(Feed.url == feed_data["url"])
            )
            existing = result.scalar_one_or_none()

            if not existing:
                feed = Feed(**feed_data)
                session.add(feed)
                print(f"添加: {feed_data['name']}")
            else:
                print(f"跳过: {feed_data['name']} (已存在)")

        await session.commit()
        print(f"\n完成! 共添加 {len(INITIAL_FEEDS)} 个 RSS 源")


if __name__ == "__main__":
    asyncio.run(init())
