import pytest
from httpx import AsyncClient


@pytest.fixture
async def guest_token1(async_client: AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/guest")
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_get_me_authenticated(async_client: AsyncClient, guest_token1: str):
    response = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "email" in data
    assert "is_active" in data
    assert "is_superuser" in data
    assert "is_verified" in data


@pytest.mark.asyncio
async def test_get_me_unauthenticated(async_client: AsyncClient):
    response = await async_client.get("/api/v1/users/me")
    assert response.status_code == 401
