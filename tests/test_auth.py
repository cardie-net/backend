import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_guest_user(async_client: AsyncClient):
    response = await async_client.post("/v1/auth/guest")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_user(async_client: AsyncClient):
    response = await async_client.post(
        "/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "supersecretpassword",
            "is_guest": False,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_login_user(async_client: AsyncClient):
    # Register first
    await async_client.post(
        "/v1/auth/register",
        json={
            "email": "testlogin@example.com",
            "password": "supersecretpassword",
            "is_guest": False,
        },
    )

    # Login
    response = await async_client.post(
        "/v1/auth/jwt/login",
        data={"username": "testlogin@example.com", "password": "supersecretpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
