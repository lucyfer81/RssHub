import json
import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Item, Preference
from app.schemas import ItemResponse, ItemUpdate
from app.services.preference import PreferenceService
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["items"])

pref_service = PreferenceService()


@router.get("", response_model=list[ItemResponse])
async def get_items(
    status: str = Query("unread"),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Item)
        .where(Item.status == status)
        .order_by(Item.score_full.desc().nullslast(), Item.score_summary.desc())
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

    # 标记已读时记录偏好
    if update.status == "read":
        try:
            text = f"{item.title or ''} {item.summary or ''}"
            keywords = await pref_service.extract_keywords(text)
            preference = Preference(
                item_id=item.id,
                feedback="read",
                keywords=json.dumps(keywords, ensure_ascii=False),
                score_diff=1.0,
            )
            session.add(preference)
            await session.commit()
        except Exception as e:
            logger.error(f"Preference recording failed for item {item.id}: {e}")

    return item
