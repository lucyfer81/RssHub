from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import make_url
from app.config import get_settings

settings = get_settings()

# 安全地转换同步 URL 为异步 URL
url = make_url(settings.database_url)
url = url.set(drivername="sqlite+aiosqlite")
async_db_url = str(url)

engine = create_async_engine(
    async_db_url,
    echo=False,
)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
