from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from sqlalchemy import select
from app.config import get_settings
from app.database import async_session
from app.models import Feed, Item
from app.services.rss_fetcher import RSSFetcher
from app.services.translator import Translator
from app.services.scorer import Scorer
from app.services.content_fetcher import ContentFetcher

settings = get_settings()


class Scheduler:
    """定时任务调度器，用于调度 RSS 同步任务"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.fetcher = RSSFetcher()
        self.content_fetcher = ContentFetcher()
        self.translator = Translator()
        self.scorer = Scorer()

    async def sync_feeds(self):
        """同步所有 RSS 源"""
        print(f"[{datetime.now()}] 开始同步 RSS 源...")

        async with async_session() as session:
            # 1. 获取所有启用的 RSS 源
            result = await session.execute(
                select(Feed).where(Feed.enabled == True)
            )
            feeds = result.scalars().all()

            if not feeds:
                print("没有启用的 RSS 源")
                return

            total_new_items = 0

            for feed in feeds:
                try:
                    print(f"正在抓取: {feed.name} ({feed.url})")

                    # 2. 抓取 RSS 内容
                    items_data = await self.fetcher.fetch(feed.url)

                    if not items_data:
                        print(f"  - 未获取到内容")
                        continue

                    new_items_count = 0

                    for item_data in items_data:
                        # 每篇文章用独立的事务，避免长时间锁定
                        async with async_session() as item_session:
                            # 3. 检查是否已存在（去重）
                            existing = await item_session.execute(
                                select(Item).where(Item.dedupe_key == item_data["dedupe_key"])
                            )
                            if existing.scalar_one_or_none():
                                continue  # 已存在，跳过

                            # 4. 创建新文章
                            new_item = Item(
                                feed_id=feed.id,
                                title=item_data["title"],
                                link=item_data["link"],
                                summary=item_data["summary"],
                                published_at=item_data.get("published_at"),
                                dedupe_key=item_data["dedupe_key"],
                                status="inbox",
                            )

                            item_session.add(new_item)

                            print(f"  - 新文章: {new_item.title[:50]}...")

                            # 5. 抓取全文
                            try:
                                full_content = await self.content_fetcher.fetch(item_data["link"])
                                if full_content:
                                    new_item.content = full_content
                            except Exception as e:
                                print(f"    - 全文抓取失败: {e}")

                            # 6. 翻译标题和摘要（暂停全文翻译）
                            try:
                                if item_data["title"]:
                                    new_item.title_zh = await self.translator.translate(
                                        item_data["title"], "中文"
                                    )
                                if item_data["summary"]:
                                    new_item.summary_zh = await self.translator.translate(
                                        item_data["summary"], "中文"
                                    )
                            except Exception as e:
                                print(f"    - 翻译失败: {e}")

                            # 7. AI 评分
                            try:
                                if item_data["title"] and item_data["summary"]:
                                    new_item.score_summary = await self.scorer.score(
                                        item_data["title"],
                                        item_data["summary"],
                                        user_preferences=""
                                    )
                            except Exception as e:
                                print(f"    - 评分失败: {e}")
                                new_item.score_summary = 50.0  # 默认分数

                            # 提交这篇文章
                            await item_session.commit()
                            new_items_count += 1

                    # 8. 更新源的同步时间
                    feed.last_synced_at = datetime.now()

                    total_new_items += new_items_count
                    print(f"  - 新增 {new_items_count} 篇文章")

                except Exception as e:
                    print(f"  - 同步失败: {e}")
                    continue

            print(f"[{datetime.now()}] 同步完成，共新增 {total_new_items} 篇文章")

    def start(self):
        """启动调度器"""
        if settings.scheduler_enabled:
            # RSS 同步任务 - 每天凌晨 0:00 执行
            self.scheduler.add_job(
                self.sync_feeds,
                CronTrigger(hour=0, minute=0),
                id="sync_feeds",
            )
            self.scheduler.start()
            print("Scheduler started - 每天 0:00 同步 RSS")
        else:
            print("Scheduler disabled")

    def stop(self):
        """停止调度器"""
        self.scheduler.shutdown()
        print("Scheduler stopped")
