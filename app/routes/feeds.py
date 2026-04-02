from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.database import get_session
from app.models import Feed
from app.schemas import FeedCreate, FeedResponse
from app.services.rss_fetcher import RSSFetcher
from app.services.feed_manager import get_feed_manager

router = APIRouter(prefix="/feeds", tags=["feeds"])

@router.get("", response_model=list[FeedResponse])
async def get_feeds(session: AsyncSession = Depends(get_session)):
    """获取所有 RSS 源列表"""
    result = await session.execute(select(Feed))
    return result.scalars().all()

@router.post("", response_model=FeedResponse)
async def create_feed(feed: FeedCreate, session: AsyncSession = Depends(get_session)):
    """创建新的 RSS 源"""
    manager = get_feed_manager()

    # 1. Write to YAML
    try:
        manager.add_to_yaml(feed.name, feed.url, feed.enabled)
    except ValueError:
        raise HTTPException(status_code=409, detail="Feed with this URL already exists")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot write to sources.yaml: {e}")

    # 2. Write to DB
    db_feed = Feed(**feed.model_dump())
    session.add(db_feed)
    try:
        await session.commit()
        await session.refresh(db_feed)
        return db_feed
    except IntegrityError:
        await session.rollback()
        manager.remove_from_yaml(feed.url)
        raise HTTPException(status_code=409, detail="Feed with this URL already exists")

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

    manager = get_feed_manager()
    try:
        manager.remove_from_yaml(feed.url)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot write to sources.yaml: {e}")

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

    manager = get_feed_manager()
    old_url = feed.url

    try:
        if old_url != feed_update.url:
            manager.remove_from_yaml(old_url)
            manager.add_to_yaml(feed_update.name, feed_update.url, feed_update.enabled)
        else:
            manager.update_in_yaml(feed_update.url, feed_update.name, feed_update.enabled)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot write to sources.yaml: {e}")

    for key, value in feed_update.model_dump().items():
        setattr(feed, key, value)

    await session.commit()
    await session.refresh(feed)
    return feed
