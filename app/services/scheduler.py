from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.config import get_settings
from app.services.rss_fetcher import RSSFetcher
from app.services.translator import Translator
from app.services.scorer import Scorer

settings = get_settings()


class Scheduler:
    """定时任务调度器，用于调度 RSS 同步任务"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        # 这些服务将在后续集成中实际使用
        self.fetcher = RSSFetcher()
        self.translator = Translator()
        self.scorer = Scorer()

    async def sync_feeds(self):
        """同步所有 RSS 源

        这里简化，实际应该从数据库获取 feeds
        """
        print("Syncing feeds...")
        # TODO: 后续集成实际的 RSS 同步逻辑
        # 1. 从数据库获取所有订阅的 RSS 源
        # 2. 使用 RSSFetcher 获取新内容
        # 3. 使用 Translator 翻译内容
        # 4. 使用 Scorer 评分
        # 5. 保存到数据库

    def start(self):
        """启动调度器"""
        if settings.scheduler_enabled:
            # RSS 同步任务
            self.scheduler.add_job(
                self.sync_feeds,
                IntervalTrigger(hours=settings.sync_interval_hours),
                id="sync_feeds",
            )
            self.scheduler.start()
            print("Scheduler started")
        else:
            print("Scheduler disabled")

    def stop(self):
        """停止调度器"""
        self.scheduler.shutdown()
        print("Scheduler stopped")
