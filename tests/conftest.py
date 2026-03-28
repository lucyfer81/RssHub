import pytest
import pytest_asyncio
import os
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# 设置测试环境变量
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_rsshub.db"
os.environ["LLM_API_KEY"] = "test_key"
os.environ["LLM_API_BASE"] = "https://api.example.com/v1"
os.environ["LLM_MODEL"] = "test_model"
os.environ["EMBEDDING_API_KEY"] = "test_key"
os.environ["EMBEDDING_API_BASE"] = "https://api.example.com/v1"
os.environ["EMBEDDING_MODEL"] = "test_model"

from app.database import Base, get_session
from app.main import app


# 创建测试数据库引擎
TEST_DATABASE_URL = "sqlite+aiosqlite:///./data/test_rsshub.db"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """创建测试数据库会话"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    """创建测试客户端"""
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def cleanup_db():
    """清理测试数据库"""
    yield
    # 测试后清理
    if os.path.exists("./data/test_rsshub.db"):
        try:
            os.remove("./data/test_rsshub.db")
        except:
            pass
