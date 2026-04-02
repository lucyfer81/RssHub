from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db, get_session
from app.models import Item
from app.routes import feeds, items, exports, shares
from app.services.scheduler import Scheduler
from app.templates_config import templates
from sqlalchemy import select

# 调度器
scheduler = Scheduler()

# 创建 FastAPI 应用
app = FastAPI(title="RssHub", version="0.1.0")

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(feeds.router)
app.include_router(items.router)
app.include_router(exports.router)
app.include_router(shares.router)

# 启动事件
@app.on_event("startup")
async def on_startup():
    await init_db()
    scheduler.start()

# 关闭事件
@app.on_event("shutdown")
async def on_shutdown():
    scheduler.stop()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/debug/scheduler")
async def debug_scheduler():
    """调试端点：检查调度器状态"""
    from app.config import get_settings
    settings = get_settings()
    return {
        "scheduler_enabled": settings.scheduler_enabled,
        "sync_interval_hours": settings.sync_interval_hours,
        "apscheduler_running": scheduler.scheduler.running,
        "apscheduler_jobs": len(scheduler.scheduler.get_jobs())
    }

@app.post("/sync")
async def manual_sync():
    """手动触发同步所有 RSS 源"""
    try:
        await scheduler.sync_feeds()
        return {"status": "success", "message": "同步完成"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 主页
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    async for session in get_session():
        result = await session.execute(
            select(Item)
            .where(Item.status == "unread")
            .order_by(Item.score_full.desc().nullslast(), Item.score_summary.desc())
        )
        items = result.scalars().all()
        break
    return templates.TemplateResponse(request, "home.html", {"items": items, "active_nav": "home"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5005)
