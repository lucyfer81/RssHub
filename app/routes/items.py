import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import async_session, get_session
from app.models import Item, Preference
from app.schemas import ItemResponse, ItemUpdate
from app.services.reading_pipeline import ReadingPipeline
from app.services.preference import PreferenceService
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["items"])

pipeline = ReadingPipeline()
pref_service = PreferenceService()


async def _run_pipeline(item_id: int, url: str, title: str, summary: str):
    """后台执行阅读 pipeline：全文抓取 → 翻译 → 摘要 → 关键要点"""
    try:
        async with async_session() as session:
            result = await pipeline.process(url, title, summary)

            db_result = await session.execute(
                select(Item).where(Item.id == item_id)
            )
            item = db_result.scalar_one_or_none()
            if not item:
                logger.warning(f"Pipeline: item {item_id} not found, skipping update")
                return

            if result.get("content"):
                item.content = result["content"]
            if result.get("content_zh"):
                item.content_zh = result["content_zh"]
            if result.get("summary_ai"):
                item.summary_ai = result["summary_ai"]
            if result.get("key_points"):
                item.key_points = json.dumps(result["key_points"], ensure_ascii=False)
            if result.get("read_time_minutes"):
                item.read_time_minutes = result["read_time_minutes"]

            await session.commit()
            logger.info(f"Pipeline completed for item {item_id}")
    except Exception as e:
        logger.error(f"Pipeline failed for item {item_id}: {e}")


@router.get("", response_model=list[ItemResponse])
async def get_items(
    status: str = Query("inbox"),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Item)
        .where(Item.status == status)
        .order_by(Item.score_summary.desc())
    )
    return result.scalars().all()


@router.get("/{item_id}", response_class=HTMLResponse)
async def get_item_detail(
    item_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    return templates.TemplateResponse(
        request, "item_detail.html", {"item": item}
    )


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    update: ItemUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.status = update.status
    await session.commit()
    await session.refresh(item)

    # 触发后续任务
    if update.status == "reading":
        asyncio.create_task(
            _run_pipeline(item.id, item.link, item.title, item.summary)
        )
    elif update.status == "discarded":
        try:
            text = f"{item.title or ''} {item.summary or ''}"
            keywords = await pref_service.extract_keywords(text)
            preference = Preference(
                item_id=item.id,
                feedback="discarded",
                keywords=json.dumps(keywords, ensure_ascii=False),
                score_diff=-1.0,
            )
            session.add(preference)
            await session.commit()
        except Exception as e:
            logger.error(f"Preference recording failed for item {item.id}: {e}")

    return item
