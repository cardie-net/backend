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
    assert data["username"].startswith("test")
    assert len(data["username"]) == 8
    assert data["display_name"] == data["username"]


@pytest.mark.asyncio
async def test_username_auto_generation_conflict(async_client: AsyncClient):
    # 'conflict' is exactly 8 chars, so no random padding should be added.
    # We expect 'conflict' and then 'conflict1'.
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
    # 'multi' is 5 chars, so they will all get 3 random digits padding.
    # Because they are random, they likely won't collide. We just check they are valid.
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
    assert data["username"].startswith("multi")
    assert len(data["username"]) == 8


@pytest.mark.asyncio
async def test_username_auto_generation_long_email(async_client: AsyncClient):
    # longusername is > 8 chars, no padding needed.
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "longusername@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "longusername"
    assert data["display_name"] == "longusername"


@pytest.mark.asyncio
async def test_username_auto_generation_short_email_padding(async_client: AsyncClient):
    # 'a' is 1 char, needs 7 random digits padding.
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    data = response.json()
    username = data["username"]
    assert username.startswith("a")
    assert len(username) == 8
    # The padding should be composed of digits
    assert username[1:].isdigit()


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
