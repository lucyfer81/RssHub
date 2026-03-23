from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Feed
from app.schemas import FeedCreate, FeedResponse
from app.services.rss_fetcher import RSSFetcher

router = APIRouter(prefix="/feeds", tags=["feeds"])

@router.get("", response_model=list[FeedResponse])
async def get_feeds(session: AsyncSession = Depends(get_session)):
    """获取所有 RSS 源列表"""
    result = await session.execute(select(Feed))
    return result.scalars().all()

@router.post("", response_model=FeedResponse)
async def create_feed(feed: FeedCreate, session: AsyncSession = Depends(get_session)):
    """创建新的 RSS 源"""
    db_feed = Feed(**feed.model_dump())
    session.add(db_feed)
    await session.commit()
    await session.refresh(db_feed)
    return db_feed

@router.post("/{feed_id}/sync")
async def sync_feed(feed_id: int, session: AsyncSession = Depends(get_session)):
    """手动同步某个源"""
    # 获取 feed
    result = await session.execute(select(Feed).where(Feed.id == feed_id))
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    # TODO: 实现同步逻辑
    # 1. 使用 RSSFetcher 获取新内容
    # 2. 去重并保存到数据库
    # 3. 更新 last_synced_at

    return {"message": "Sync started", "feed_id": feed_id}

@router.delete("/{feed_id}")
async def delete_feed(feed_id: int, session: AsyncSession = Depends(get_session)):
    """删除 RSS 源"""
    result = await session.execute(select(Feed).where(Feed.id == feed_id))
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    await session.delete(feed)
    await session.commit()
    return {"message": "Feed deleted", "feed_id": feed_id}

@router.patch("/{feed_id}", response_model=FeedResponse)
async def update_feed(feed_id: int, feed_update: FeedCreate, session: AsyncSession = Depends(get_session)):
    """更新 RSS 源"""
    result = await session.execute(select(Feed).where(Feed.id == feed_id))
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    for key, value in feed_update.model_dump().items():
        setattr(feed, key, value)

    await session.commit()
    await session.refresh(feed)
    return feed
