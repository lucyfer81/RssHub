from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_session
from app.models import Item

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("/items/{item_id}/markdown")
async def export_markdown(item_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    markdown = f"""# {item.title_zh or item.title}

**原文链接**: {item.link}

## 摘要

{item.summary_zh or item.summary}

## AI 总结

{item.summary_ai or '暂无'}

## 全文

{item.content_zh or item.content}

---

*由 RssHub 生成*
"""

    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={item.id}.md"}
    )
