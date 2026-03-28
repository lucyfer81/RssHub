from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Item
from app.schemas import ItemResponse, ItemUpdate
from app.templates_config import templates

router = APIRouter(prefix="/items", tags=["items"])


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
        # 触发抓取全文、翻译、总结
        pass
    elif update.status == "discarded":
        # 记录偏好学习
        pass

    return item
