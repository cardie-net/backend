import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from src.database import get_db
from src.main import app

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="function")
async def async_session() -> AsyncSession:
    """Creates a fresh database for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def async_client(async_session: AsyncSession) -> AsyncClient:
    """Returns an async HTTP client that uses our test database."""

    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    class CookieInjectingTransport(ASGITransport):
        async def handle_async_request(self, request):
            token = request.headers.get("x-test-cookie")
            if token:
                request.headers["cookie"] = f"cardie_session={token}"
            return await super().handle_async_request(request)

    async with AsyncClient(
        transport=CookieInjectingTransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        yield client


from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_send_email():
    with patch("src.auth.user_manager.send_email") as mock:
        yield mock
