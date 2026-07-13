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


import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_username_auto_generation(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "test"
    assert data["display_name"] == "test"


@pytest.mark.asyncio
async def test_username_auto_generation_conflict(async_client: AsyncClient):
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "conflict@example.com", "password": "password123"},
    )
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "conflict@other.com", "password": "password123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "conflict1"


@pytest.mark.asyncio
async def test_username_auto_generation_conflict_multiple(async_client: AsyncClient):
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "multi@example.com", "password": "password123"},
    )
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "multi@other.com", "password": "password123"},
    )
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "multi@third.com", "password": "password123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "multi2"


@pytest.mark.asyncio
async def test_patch_user(async_client: AsyncClient, guest_token1: str):
    # Patch username and display_name using guest token
    token = guest_token1
    response = await async_client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "newusername", "display_name": "New Display Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "newusername"
    assert data["display_name"] == "New Display Name"


@pytest.mark.asyncio
async def test_patch_user_validation(async_client: AsyncClient, guest_token1: str):
    token = guest_token1

    # Invalid username (too short)
    response = await async_client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "short"},
    )
    assert response.status_code == 422

    # Invalid username (not url safe)
    response = await async_client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "invalid username!"},
    )
    assert response.status_code == 422

    # Invalid display_name (too long)
    response = await async_client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"display_name": "a" * 81},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_user_profile_success(async_client: AsyncClient, guest_token1: str):
    # First, get the me data to find the generated username
    response = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code == 200
    user_data = response.json()
    username = user_data["username"]

    # Now test the profile endpoint
    profile_response = await async_client.get(f"/api/v1/users/profile/{username}")
    assert profile_response.status_code == 200
    profile_data = profile_response.json()
    assert profile_data["username"] == username
    assert profile_data["id"] == user_data["id"]


@pytest.mark.asyncio
async def test_get_user_profile_not_found(async_client: AsyncClient):
    response = await async_client.get("/api/v1/users/profile/nonexistentusername")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "User not found"
