import pytest
from httpx import AsyncClient

from tests.conftest import extract_email_token


@pytest.mark.asyncio
async def test_create_guest_user(async_client: AsyncClient):
    response = await async_client.post("/api/v1/auth/guest")
    assert response.status_code == 204
    assert "cardie_session" in response.cookies


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
async def test_login_user_unverified(async_client: AsyncClient):
    # Register first
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "testlogin@example.com",
            "password": "supersecretpassword",
            "is_guest": False,
        },
    )

    # Login should fail because unverified
    response = await async_client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "testlogin@example.com", "password": "supersecretpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "USER_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_login_verified_user(async_client: AsyncClient, mock_send_email):
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "testloginverified@example.com",
            "password": "supersecretpassword",
            "is_guest": False,
        },
    )

    captured_token = extract_email_token(mock_send_email)

    # Verify
    await async_client.post("/api/v1/auth/verify", json={"token": captured_token})

    # Login should succeed now
    response = await async_client.post(
        "/api/v1/auth/jwt/login",
        data={
            "username": "testloginverified@example.com",
            "password": "supersecretpassword",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 204
    assert "cardie_session" in response.cookies


@pytest.mark.asyncio
async def test_user_verification_flow(async_client: AsyncClient, mock_send_email):
    # Register
    reg_response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "testverify@example.com",
            "password": "supersecretpassword",
            "is_guest": False,
        },
    )
    assert reg_response.status_code == 201

    captured_token = extract_email_token(mock_send_email)

    # Missing token
    resp = await async_client.post("/api/v1/auth/verify", json={})
    assert resp.status_code == 422

    # Invalid token
    resp = await async_client.post(
        "/api/v1/auth/verify", json={"token": "invalid_token"}
    )
    assert resp.status_code == 400

    # Valid token
    resp = await async_client.post(
        "/api/v1/auth/verify", json={"token": captured_token}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_verified"] is True
    assert data["email"] == "testverify@example.com"

    # Already verified
    resp = await async_client.post(
        "/api/v1/auth/verify", json={"token": captured_token}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "VERIFY_USER_BAD_TOKEN"


@pytest.mark.asyncio
async def test_forgot_password_flow(async_client: AsyncClient, mock_send_email):
    # Register & verify
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "forgot@example.com",
            "password": "oldpassword",
            "is_guest": False,
        },
    )
    captured_token = extract_email_token(mock_send_email)

    await async_client.post("/api/v1/auth/verify", json={"token": captured_token})

    forgot_response = await async_client.post(
        "/api/v1/auth/forgot-password", json={"email": "forgot@example.com"}
    )
    assert forgot_response.status_code == 202

    captured_token = extract_email_token(mock_send_email)

    reset_response = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": captured_token, "password": "newpassword123"},
    )
    assert reset_response.status_code == 200

    # Test login with new password
    login_response = await async_client.post(
        "/api/v1/auth/jwt/login",
        data={
            "username": "forgot@example.com",
            "password": "newpassword123",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_response.status_code == 204
    assert "cardie_session" in login_response.cookies


@pytest.mark.asyncio
async def test_resend_verification(async_client: AsyncClient, mock_send_email):
    # Register
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "resend@example.com",
            "password": "supersecretpassword",
            "is_guest": False,
        },
    )

    # First verification email sent. Clear the mock history to cleanly test resend.
    mock_send_email.reset_mock()

    resend_resp = await async_client.post(
        "/api/v1/auth/request-verify-token", json={"email": "resend@example.com"}
    )
    assert resend_resp.status_code == 202

    # Check if a new email was sent
    assert mock_send_email.called
    captured_token = extract_email_token(mock_send_email)
    assert captured_token is not None
