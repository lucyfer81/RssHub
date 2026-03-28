from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Item, Share
from app.schemas import ShareResponse
import secrets
from datetime import datetime, timedelta

router = APIRouter(prefix="/shares", tags=["shares"])


@router.post("/items/{item_id}", response_model=ShareResponse)
async def create_share(item_id: int, session: AsyncSession = Depends(get_session)):
    share_code = secrets.token_urlsafe(8)
    expires_at = datetime.now() + timedelta(days=30)

    share = Share(item_id=item_id, share_code=share_code, expires_at=expires_at)
    session.add(share)
    await session.commit()
    await session.refresh(share)

    return share


@router.get("/items/{item_id}")
async def get_share(item_id: int):
    return {"share_url": f"/share/{item_id}"}


@router.get("/{code}")
async def share_page(code: str, request: Request):
    from app.database import async_session
    async with async_session() as session:
        result = await session.execute(
            select(Share).join(Item).where(Share.share_code == code)
        )
        share = result.scalar_one_or_none()
        if not share:
            return {"error": "分享链接不存在或已过期"}

        item_result = await session.execute(select(Item).where(Item.id == share.item_id))
        item = item_result.scalar_one()

    from app.templates_config import templates
    return templates.TemplateResponse(request, "share.html", {"item": item})
