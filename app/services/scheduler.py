import re
import json
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from sqlalchemy import select
from app.config import get_settings
from app.database import async_session
from app.models import Feed, Item
from app.services.rss_fetcher import RSSFetcher
from app.services.scorer import Scorer
from app.services.content_fetcher import ContentFetcher
from app.services.summarizer import Summarizer
from app.services.article_store import ArticleStore
from app.services.feed_manager import get_feed_manager

settings = get_settings()


class Scheduler:
    """定时任务调度器，两阶段流水线：摘要评分 → 全文处理"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.fetcher = RSSFetcher()
        self.content_fetcher = ContentFetcher()
        self.scorer = Scorer()
        self.summarizer = Summarizer()
        self.article_store = ArticleStore()

    async def sync_feeds(self):
        """两阶段流水线"""
        print(f"[{datetime.now()}] 开始同步 RSS 源...")
        await self._phase1_fetch_and_score_summary()
        await self._phase2_fetch_full_and_score()
        print(f"[{datetime.now()}] 同步完成")

    async def _phase1_fetch_and_score_summary(self):
        """Phase 1: RSS Fetch + Summary Scoring (lightweight)"""
        print(f"[{datetime.now()}] Phase 1: 抓取 RSS + 摘要评分...")

        manager = get_feed_manager()
        yaml_feeds = manager.read_yaml()
        enabled_feeds = [f for f in yaml_feeds if f.enabled]

        if not enabled_feeds:
            print("  没有启用的 RSS 源")
            return

        async with async_session() as session:
            # Build URL -> DB Feed lookup
            urls = [f.url for f in enabled_feeds]
            result = await session.execute(
                select(Feed).where(Feed.url.in_(urls))
            )
            db_feeds_by_url = {f.url: f for f in result.scalars().all()}

            total_new_items = 0

            for yaml_feed in enabled_feeds:
                try:
                    feed = db_feeds_by_url.get(yaml_feed.url)
                    if feed is None:
                        # Create DB row on the fly
                        feed = Feed(name=yaml_feed.name, url=yaml_feed.url, enabled=True)
                        session.add(feed)
                        await session.flush()
                        db_feeds_by_url[yaml_feed.url] = feed

                    print(f"  正在抓取: {yaml_feed.name} ({yaml_feed.url})")

                    # 抓取 RSS 内容
                    items_data = await self.fetcher.fetch(yaml_feed.url)

                    if not items_data:
                        print(f"    - 未获取到内容")
                        continue

                    new_items_count = 0

                    for item_data in items_data:
                        # 每篇文章用独立的事务
                        async with async_session() as item_session:
                            try:
                                # 去重检查
                                existing = await item_session.execute(
                                    select(Item).where(
                                        Item.dedupe_key == item_data["dedupe_key"]
                                    )
                                )
                                if existing.scalar_one_or_none():
                                    continue

                                # 创建新文章
                                new_item = Item(
                                    feed_id=feed.id,
                                    title=item_data["title"],
                                    link=item_data["link"],
                                    summary=item_data["summary"],
                                    published_at=item_data.get("published_at"),
                                    dedupe_key=item_data["dedupe_key"],
                                    status="unread",
                                )

                                # 摘要评分
                                try:
                                    if item_data["title"] and item_data["summary"]:
                                        new_item.score_summary = await self.scorer.score(
                                            item_data["title"],
                                            item_data["summary"],
                                        )
                                    else:
                                        new_item.score_summary = 50.0
                                except Exception as e:
                                    print(f"      - 摘要评分失败: {e}")
                                    new_item.score_summary = 50.0

                                item_session.add(new_item)
                                await item_session.commit()
                                new_items_count += 1
                                print(
                                    f"    - 新文章: {new_item.title[:50]}... (score: {new_item.score_summary})"
                                )

                            except Exception as e:
                                await item_session.rollback()
                                print(f"      - 处理失败: {e}")
                                continue

                    # 更新源的同步时间
                    feed.last_synced_at = datetime.now()
                    await session.commit()

                    total_new_items += new_items_count
                    print(f"    - 新增 {new_items_count} 篇文章")

                except Exception as e:
                    print(f"    - 同步失败: {e}")
                    continue

            print(
                f"[{datetime.now()}] Phase 1 完成，共新增 {total_new_items} 篇文章"
            )

    async def _phase2_fetch_full_and_score(self):
        """Phase 2: Full-Text Fetch + Full-Text Scoring (heavy, sorted by score)"""
        print(f"[{datetime.now()}] Phase 2: 全文抓取 + 全文评分...")

        async with async_session() as session:
            # 查询所有未进行全文评分的文章，按摘要评分降序排列
            result = await session.execute(
                select(Item, Feed.name)
                .join(Feed, Item.feed_id == Feed.id)
                .where(Item.score_full.is_(None))
                .order_by(Item.score_summary.desc())
            )
            rows = result.all()

            if not rows:
                print("  没有需要全文处理的文章")
                return

            print(f"  待处理文章数: {len(rows)}")

            processed = 0
            for item, feed_name in rows:
                try:
                    # 1. 抓取全文
                    content = await self.content_fetcher.fetch(item.link)
                    if not content:
                        print(f"  - 跳过（无法获取全文）: {item.title[:50]}...")
                        continue

                    item.content = content

                    # 2. 全文评分
                    try:
                        item.score_full = await self.scorer.score_full(
                            item.title, content
                        )
                    except Exception as e:
                        print(f"    - 全文评分失败: {e}")
                        item.score_full = item.score_summary

                    # 3. AI 摘要
                    try:
                        item.summary_ai = await self.summarizer.summarize(
                            content[:4000]
                        )
                    except Exception as e:
                        print(f"    - AI 摘要失败: {e}")

                    # 4. 提取关键要点
                    try:
                        item.key_points = await self._extract_key_points(
                            content[:4000]
                        )
                    except Exception as e:
                        print(f"    - 关键要点提取失败: {e}")

                    # 5. 阅读时长估算
                    item.read_time_minutes = self._estimate_read_time(content)

                    # 6. 保存为 Markdown 文件
                    relative_path = self.article_store.save(
                        item, content, feed_name
                    )
                    item.article_path = relative_path

                    # 7. 提交
                    await session.commit()
                    processed += 1
                    print(
                        f"  - 已处理: {item.title[:50]}... "
                        f"(score_full: {item.score_full})"
                    )

                except Exception as e:
                    await session.rollback()
                    print(f"  - 全文处理失败 ({item.title[:30]}...): {e}")
                    continue

            print(
                f"[{datetime.now()}] Phase 2 完成，共处理 {processed}/{len(rows)} 篇文章"
            )

    async def _extract_key_points(self, content: str) -> str:
        """使用 LLM 提取文章关键要点，返回 JSON 字符串"""
        prompt = f"""请从以下文章中提取 3-5 个最关键的要点。每个要点用一句话概括。
直接返回要点列表，每行一个要点，不要编号，不要其他内容。

文章内容：
{content}
"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            result = response.json()
            text = result["choices"][0]["message"]["content"].strip()

            points = [
                line.strip().lstrip("-•* ") for line in text.split("\n") if line.strip()
            ]
            points = [p for p in points if p][:5]
            return json.dumps(points, ensure_ascii=False)

    def _estimate_read_time(self, text: str) -> int:
        """估算阅读时长（分钟）

        中文：约 400 字/分钟
        英文：约 250 词/分钟
        """
        if not text:
            return 0

        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        if chinese_chars > 0:
            return max(1, round(chinese_chars / 400))
        else:
            word_count = len(text.split())
            return max(1, round(word_count / 250))

    def start(self):
        """启动调度器"""
        if settings.scheduler_enabled:
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
