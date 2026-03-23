from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from app.database import init_db, get_session
from app.models import Item
from app.routes import feeds, items, exports, shares
from app.services.scheduler import Scheduler
from sqlalchemy import select

# 模板
templates = Jinja2Templates(directory="app/templates")

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

# 健康检查
@app.get("/")
async def root():
    return {"message": "RssHub API", "version": "0.1.0"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Inbox 页面
@app.get("/inbox")
async def inbox(request: Request):
    from app.database import get_session
    from fastapi.templating import Jinja2Templates

    # 每次请求创建新的 templates 对象
    templates = Jinja2Templates(directory="app/templates")

    async for session in get_session():
        result = await session.execute(
            select(Item)
            .where(Item.status == "inbox")
            .order_by(Item.score_summary.desc())
        )
        items = result.scalars().all()
        break
    # Starlette 1.0.0+ 需要传递 request 作为第一个参数
    return templates.TemplateResponse(request, "inbox.html", {"items": items})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
