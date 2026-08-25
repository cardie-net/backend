import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.auth import google_oauth_router
from src.auth.service import handle_oauth_callback
from src.models import Deck, OAuthAccount, User
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
    assert response.status_code == 202
    data = response.json()
    assert data["msg"] == "Verification email sent"


@pytest.mark.asyncio
async def test_login_before_verification_fails(async_client: AsyncClient):
    # Register only stages the credentials; no usable account exists yet
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "testlogin@example.com",
            "password": "supersecretpassword",
            "is_guest": False,
        },
    )

    # Unverified accounts cannot exist, so this is plain bad credentials
    response = await async_client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "testlogin@example.com", "password": "supersecretpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "LOGIN_BAD_CREDENTIALS"


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
    assert reg_response.status_code == 202

    captured_token = extract_email_token(mock_send_email)

    # Missing token
    resp = await async_client.post("/api/v1/auth/verify", json={})
    assert resp.status_code == 422

    # Invalid token
    resp = await async_client.post(
        "/api/v1/auth/verify", json={"token": "invalid_token"}
    )
    assert resp.status_code == 400

    # Valid token promotes the staged registration into a real account
    resp = await async_client.post(
        "/api/v1/auth/verify", json={"token": captured_token}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_verified"] is True
    assert data["is_guest"] is False
    assert data["email"] == "testverify@example.com"

    # Token is single use: the pending registration was consumed
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

    # Clear the mock history so the reset email is the next captured one
    mock_send_email.reset_mock()

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

    # The resent token still promotes the same staged registration
    verify_resp = await async_client.post(
        "/api/v1/auth/verify", json={"token": captured_token}
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["email"] == "resend@example.com"


GUEST_PASSWORD = "supersecretpassword"


@pytest.mark.asyncio
async def test_register_upgrades_guest_keeps_data(
    async_client: AsyncClient, mock_send_email
):
    # Guest session with a deck, a card and learning progress
    guest_resp = await async_client.post("/api/v1/auth/guest")
    assert guest_resp.status_code == 204
    guest_cookie = guest_resp.cookies.get("cardie_session")
    guest_headers = {"X-Test-Cookie": guest_cookie}

    me_resp = await async_client.get("/api/v1/users/me", headers=guest_headers)
    assert me_resp.json()["is_guest"] is True
    guest_id = me_resp.json()["id"]

    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Guest Deck", "privacy": "private"},
        headers=guest_headers,
    )
    assert deck_resp.status_code == 200
    deck_id = deck_resp.json()["id"]

    card_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={
            "front": [{"type": "text", "content": "front"}],
            "back": [{"type": "text", "content": "back"}],
        },
        headers=guest_headers,
    )
    assert card_resp.status_code == 200
    card_id = card_resp.json()["id"]

    progress_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/progress",
        json={"progress": [{"card_id": str(card_id), "box": 3}]},
        headers=guest_headers,
    )
    assert progress_resp.status_code == 204

    # Signing up only stages the registration; the account stays a guest
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "upgraded@example.com", "password": GUEST_PASSWORD},
        headers=guest_headers,
    )
    assert reg_resp.status_code == 202
    assert mock_send_email.called

    # The session still resolves to the same untouched guest account:
    # full access while the verification is pending.
    me_resp = await async_client.get("/api/v1/users/me", headers=guest_headers)
    assert me_resp.json()["id"] == guest_id
    assert me_resp.json()["is_guest"] is True

    # All guest data is still reachable
    items_resp = await async_client.get(
        f"/api/v1/users/{guest_id}/items", headers=guest_headers
    )
    assert items_resp.status_code == 200
    deck_ids = [item["id"] for item in items_resp.json()]
    assert deck_id in deck_ids

    cards_resp = await async_client.get(
        f"/api/v1/decks/{deck_id}/cards", headers=guest_headers
    )
    assert [c["id"] for c in cards_resp.json()] == [card_id]

    progress_resp = await async_client.get(
        f"/api/v1/decks/{deck_id}/progress", headers=guest_headers
    )
    assert progress_resp.json() == [{"card_id": card_id, "box": 3}]

    # Verifying promotes the same user row in place: same id, so all data
    # carries over and the live session cookie keeps working.
    captured_token = extract_email_token(mock_send_email)
    verify_resp = await async_client.post(
        "/api/v1/auth/verify", json={"token": captured_token}
    )
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert data["id"] == guest_id
    assert data["is_guest"] is False
    assert data["is_verified"] is True
    assert data["email"] == "upgraded@example.com"

    me_resp = await async_client.get("/api/v1/users/me", headers=guest_headers)
    assert me_resp.json()["id"] == guest_id
    assert me_resp.json()["is_guest"] is False
    assert me_resp.json()["is_verified"] is True

    # All data carried over through promotion
    items_resp = await async_client.get(
        f"/api/v1/users/{guest_id}/items", headers=guest_headers
    )
    assert deck_id in [item["id"] for item in items_resp.json()]
    progress_resp = await async_client.get(
        f"/api/v1/decks/{deck_id}/progress", headers=guest_headers
    )
    assert progress_resp.json() == [{"card_id": card_id, "box": 3}]

    # Login works right after verification (password from signup form)
    login_resp = await async_client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "upgraded@example.com", "password": GUEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_resp.status_code == 204


@pytest.mark.asyncio
async def test_register_guest_email_conflict(async_client: AsyncClient):
    # A real account already uses this email
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "taken@example.com", "password": GUEST_PASSWORD},
    )

    guest_resp = await async_client.post("/api/v1/auth/guest")
    guest_cookie = guest_resp.cookies.get("cardie_session")
    guest_headers = {"X-Test-Cookie": guest_cookie}

    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "taken@example.com", "password": GUEST_PASSWORD},
        headers=guest_headers,
    )
    assert reg_resp.status_code == 400
    assert reg_resp.json()["detail"] == "REGISTER_USER_ALREADY_EXISTS"

    # Guest account is unchanged
    me_resp = await async_client.get("/api/v1/users/me", headers=guest_headers)
    assert me_resp.json()["is_guest"] is True
    assert me_resp.json()["email"].startswith("guest_")


@pytest.mark.asyncio
async def test_register_guest_username_conflict(async_client: AsyncClient):
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "password": GUEST_PASSWORD,
            "username": "takenusername",
        },
    )

    guest_resp = await async_client.post("/api/v1/auth/guest")
    guest_cookie = guest_resp.cookies.get("cardie_session")
    guest_headers = {"X-Test-Cookie": guest_cookie}

    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": GUEST_PASSWORD,
            "username": "takenusername",
        },
        headers=guest_headers,
    )
    assert reg_resp.status_code == 400
    assert reg_resp.json()["detail"] == "REGISTER_USER_ALREADY_EXISTS"

    me_resp = await async_client.get("/api/v1/users/me", headers=guest_headers)
    assert me_resp.json()["is_guest"] is True


@pytest.mark.asyncio
async def test_register_without_guest_session_stages_registration(
    async_client: AsyncClient,
):
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "fresh@example.com", "password": GUEST_PASSWORD},
    )
    assert response.status_code == 202
    assert response.json()["msg"] == "Verification email sent"


@pytest.mark.asyncio
async def test_login_discards_guest_data(
    async_client: AsyncClient, async_session: AsyncSession, mock_send_email
):
    # Real account (registered + verified)
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "real@example.com", "password": GUEST_PASSWORD},
    )
    captured_token = extract_email_token(mock_send_email)
    await async_client.post("/api/v1/auth/verify", json={"token": captured_token})

    # Guest session with data on the same client
    guest_resp = await async_client.post("/api/v1/auth/guest")
    guest_cookie = guest_resp.cookies.get("cardie_session")
    guest_headers = {"X-Test-Cookie": guest_cookie}
    me_resp = await async_client.get("/api/v1/users/me", headers=guest_headers)
    guest_id = uuid.UUID(me_resp.json()["id"])

    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Guest Deck", "privacy": "private"},
        headers=guest_headers,
    )
    assert deck_resp.status_code == 200
    deck_id = uuid.UUID(deck_resp.json()["id"])

    # Logging in while the guest session cookie is present discards the guest
    login_resp = await async_client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "real@example.com", "password": GUEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_resp.status_code == 204

    # Guest account and all its data are gone (no merging)
    result = await async_session.execute(
        select(User)
        .where(User.id == guest_id)
        .execution_options(populate_existing=True)
    )
    assert result.scalars().first() is None
    deck_result = await async_session.execute(
        select(Deck).where(Deck.id == deck_id).execution_options(populate_existing=True)
    )
    assert deck_result.scalars().first() is None
    # The real account is untouched and now owns the session
    me_resp = await async_client.get("/api/v1/users/me")
    assert me_resp.json()["email"] == "real@example.com"
    assert me_resp.json()["is_guest"] is False


@pytest.mark.asyncio
async def test_failed_login_preserves_guest(
    async_client: AsyncClient, async_session: AsyncSession
):
    guest_resp = await async_client.post("/api/v1/auth/guest")
    guest_cookie = guest_resp.cookies.get("cardie_session")
    guest_headers = {"X-Test-Cookie": guest_cookie}
    me_resp = await async_client.get("/api/v1/users/me", headers=guest_headers)
    guest_id = uuid.UUID(me_resp.json()["id"])

    login_resp = await async_client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "nobody@example.com", "password": "wrongpassword1"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_resp.status_code == 400

    # Guest still exists after a failed login
    result = await async_session.execute(
        select(User)
        .where(User.id == guest_id)
        .execution_options(populate_existing=True)
    )
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_oauth_callback_upgrades_guest(async_session: AsyncSession):
    guest = User(
        email="oauthguest@guest.example.com",
        hashed_password="unused",
        username="oauthguestone",
        display_name="oauthguestone",
        is_guest=True,
    )
    async_session.add(guest)
    await async_session.commit()
    await async_session.refresh(guest)
    guest_id = guest.id

    user = await handle_oauth_callback(
        db=async_session,
        oauth_name="google",
        access_token="token1",
        account_id="google-id-1",
        account_email="oauth.upgraded@gmail.com",
        guest_user=guest,
    )
    assert user.id == guest_id
    assert user.is_guest is False
    assert user.is_verified is True
    assert user.email == "oauth.upgraded@gmail.com"

    oauth = (
        await async_session.execute(
            select(OAuthAccount).where(OAuthAccount.account_id == "google-id-1")
        )
    ).scalar_one()
    assert oauth.user_id == guest_id
    assert oauth.account_email == "oauth.upgraded@gmail.com"


@pytest.mark.asyncio
async def test_oauth_callback_existing_account_discards_guest(
    async_session: AsyncSession,
):
    real = User(
        email="real.google@gmail.com",
        hashed_password="unused",
        username="realgoogleuser",
        display_name="realgoogleuser",
        is_guest=False,
        is_verified=True,
    )
    async_session.add(real)
    await async_session.commit()
    await async_session.refresh(real)
    real_id = real.id

    async_session.add(
        OAuthAccount(
            oauth_name="google",
            access_token="existing-token",
            account_id="google-id-2",
            account_email="real.google@gmail.com",
            user_id=real_id,
        )
    )
    guest = User(
        email="oauthguest2@guest.example.com",
        hashed_password="unused",
        username="oauthguesttwo",
        display_name="oauthguesttwo",
        is_guest=True,
    )
    async_session.add(guest)
    await async_session.commit()
    await async_session.refresh(guest)
    guest_id = guest.id

    user = await handle_oauth_callback(
        db=async_session,
        oauth_name="google",
        access_token="new-token",
        account_id="google-id-2",
        account_email="real.google@gmail.com",
        guest_user=guest,
    )
    assert user.id == real_id
    result = await async_session.execute(
        select(User)
        .where(User.id == guest_id)
        .execution_options(populate_existing=True)
    )
    assert result.scalars().first() is None


@pytest.mark.asyncio
async def test_oauth_callback_existing_email_signs_in_and_discards_guest(
    async_session: AsyncSession,
):
    real = User(
        email="owner@gmail.com",
        hashed_password="unused",
        username="ownergoogleuser",
        display_name="ownergoogleuser",
        is_guest=False,
        is_verified=True,
    )
    async_session.add(real)
    await async_session.commit()
    await async_session.refresh(real)
    real_id = real.id

    guest = User(
        email="oauthguest3@guest.example.com",
        hashed_password="unused",
        username="oauthguestthree",
        display_name="oauthguestthree",
        is_guest=True,
    )
    async_session.add(guest)
    await async_session.commit()
    await async_session.refresh(guest)
    guest_id = guest.id

    user = await handle_oauth_callback(
        db=async_session,
        oauth_name="google",
        access_token="token3",
        account_id="google-id-3",
        account_email="owner@gmail.com",
        guest_user=guest,
    )
    assert user.id == real_id
    # OAuth identity is linked to the existing account...
    oauth = (
        await async_session.execute(
            select(OAuthAccount).where(OAuthAccount.account_id == "google-id-3")
        )
    ).scalar_one()
    assert oauth.user_id == real_id
    # ...and the guest session is discarded, not merged
    result = await async_session.execute(
        select(User)
        .where(User.id == guest_id)
        .execution_options(populate_existing=True)
    )
    assert result.scalars().first() is None


# --- Google OAuth redirect_uri construction ---


def _redirect_uri_from(response) -> str:
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["redirect_uri"][0]


@pytest.mark.asyncio
async def test_oauth_authorize_uses_request_scheme_by_default(
    async_client: AsyncClient, monkeypatch
):
    """Without PUBLIC_BACKEND_URL the callback URL is derived from the request."""
    monkeypatch.setattr(google_oauth_router.settings, "PUBLIC_BACKEND_URL", "")
    response = await async_client.get(
        "/api/v1/auth/google/authorize", follow_redirects=False
    )
    assert response.status_code == 307
    assert _redirect_uri_from(response) == "http://test/api/v1/auth/google/callback"


@pytest.mark.asyncio
async def test_oauth_authorize_uses_public_backend_url(
    async_client: AsyncClient, monkeypatch
):
    """PUBLIC_BACKEND_URL overrides scheme/host (e.g. behind a reverse proxy)."""
    monkeypatch.setattr(
        google_oauth_router.settings, "PUBLIC_BACKEND_URL", "https://cardie.net"
    )
    response = await async_client.get(
        "/api/v1/auth/google/authorize", follow_redirects=False
    )
    assert response.status_code == 307
    assert (
        _redirect_uri_from(response) == "https://cardie.net/api/v1/auth/google/callback"
    )


@pytest.mark.asyncio
async def test_oauth_authorize_cookie_secure_flag(
    async_client: AsyncClient, monkeypatch
):
    """The CSRF cookie carries the Secure flag when COOKIE_SECURE is enabled."""
    monkeypatch.setattr(google_oauth_router.settings, "COOKIE_SECURE", True)
    response = await async_client.get(
        "/api/v1/auth/google/authorize", follow_redirects=False
    )
    assert response.status_code == 307
    assert "Secure" in response.headers["set-cookie"]
