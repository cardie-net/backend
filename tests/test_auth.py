from unittest.mock import patch

import pytest
from httpx import AsyncClient

from src.auth.user_manager import UserManager


@pytest.mark.asyncio
async def test_create_guest_user(async_client: AsyncClient):
    response = await async_client.post("/api/v1/auth/guest")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_user(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/register",
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
        "/api/v1/auth/register",
        json={
            "email": "testlogin@example.com",
            "password": "supersecretpassword",
            "is_guest": False,
        },
    )

    # Login
    response = await async_client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "testlogin@example.com", "password": "supersecretpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_user_verification_flow(async_client: AsyncClient):
    captured_token = None
    original_on_after_request_verify = UserManager.on_after_request_verify

    async def mock_on_after_request_verify(self, user, token, request=None):
        nonlocal captured_token
        captured_token = token
        await original_on_after_request_verify(self, user, token, request)

    with patch.object(
        UserManager, "on_after_request_verify", new=mock_on_after_request_verify
    ):
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "verifytest@example.com",
                "password": "supersecretpassword",
                "is_guest": False,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "verifytest@example.com"
        assert data["is_verified"] is False

        assert captured_token is not None, "Verification token was not captured"

        verify_response = await async_client.post(
            "/api/v1/auth/verify", json={"token": captured_token}
        )
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["is_verified"] is True
