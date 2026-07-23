import pytest
from httpx import AsyncClient


@pytest.fixture
async def guest_token1(async_client: AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/guest")
    return response.cookies.get("cardie_session")


@pytest.mark.asyncio
async def test_get_me_authenticated(async_client: AsyncClient, guest_token1: str):
    response = await async_client.get(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "email" in data
    assert "is_active" in data
    assert "is_superuser" in data
    assert "is_verified" in data
    assert "username" in data
    assert data["username"].startswith("guest_")
    assert len(data["username"]) <= 32


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
async def test_username_auto_generation_very_long_email_truncation(
    async_client: AsyncClient,
):
    long_prefix = "a" * 40
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": f"{long_prefix}@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "a" * 26
    assert data["display_name"] == "a" * 26


@pytest.mark.asyncio
async def test_username_auto_generation_very_long_email_conflict(
    async_client: AsyncClient,
):
    long_prefix = "b" * 40
    # First user
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": f"{long_prefix}@example.com", "password": "password123"},
    )
    # Second user, should get a conflict and append "1"
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": f"{long_prefix}@other.com", "password": "password123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == ("b" * 26) + "1"


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
        headers={"X-Test-Cookie": token},
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
        headers={"X-Test-Cookie": token},
        json={"username": "short"},
    )
    assert response.status_code == 422

    # Invalid username (not url safe)
    response = await async_client.patch(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": token},
        json={"username": "invalid username!"},
    )
    assert response.status_code == 422

    # Invalid display_name (too long)
    response = await async_client.patch(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": token},
        json={"display_name": "a" * 81},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_user_profile_success(async_client: AsyncClient, guest_token1: str):
    # First, get the me data to find the generated username
    response = await async_client.get(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": guest_token1},
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


from unittest.mock import patch


@pytest.mark.asyncio
async def test_upload_avatar(async_client: AsyncClient, guest_token1: str):
    # Create a dummy image
    import io

    from PIL import Image

    img = Image.new("RGB", (100, 100), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    files = {"file": ("test.jpg", img_bytes, "image/jpeg")}

    with patch(
        "src.routers.users.upload_file_to_s3",
        return_value="http://test-url/avatar.webp",
    ):
        response = await async_client.post(
            "/api/v1/users/me/avatar",
            headers={"X-Test-Cookie": guest_token1},
            files=files,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["avatar_url"] == "http://test-url/avatar.webp"


@pytest.mark.asyncio
async def test_get_user_profile_default_properties(
    async_client: AsyncClient, guest_token1: str
):
    # First, get the me data to find the generated username
    response = await async_client.get(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": guest_token1},
    )
    user_data = response.json()
    username = user_data["username"]

    profile_response = await async_client.get(f"/api/v1/users/profile/{username}")
    assert profile_response.status_code == 200
    profile_data = profile_response.json()

    assert "bio" in profile_data
    assert profile_data["bio"] is None or profile_data["bio"] == ""
    assert "social_links" in profile_data
    assert profile_data["social_links"] == {} or profile_data["social_links"] is None


@pytest.mark.asyncio
async def test_patch_user_properties(async_client: AsyncClient, guest_token1: str):
    token = guest_token1
    response = await async_client.patch(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": token},
        json={
            "bio": "This is my new bio!",
            "social_links": {
                "instagram": "https://instagram.com/myprofile",
                "facebook": "https://facebook.com/myprofile",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["bio"] == "This is my new bio!"
    assert data["social_links"]["instagram"] == "https://instagram.com/myprofile"
    assert data["social_links"]["facebook"] == "https://facebook.com/myprofile"

    # Also verify it updates the profile
    username = data["username"]
    profile_response = await async_client.get(f"/api/v1/users/profile/{username}")
    assert profile_response.status_code == 200
    profile_data = profile_response.json()
    assert profile_data["bio"] == "This is my new bio!"
    assert (
        profile_data["social_links"]["instagram"] == "https://instagram.com/myprofile"
    )
    assert profile_data["social_links"]["facebook"] == "https://facebook.com/myprofile"


@pytest.mark.asyncio
async def test_patch_user_invalid_social_link_url(
    async_client: AsyncClient, guest_token1: str
):
    token = guest_token1
    response = await async_client.patch(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": token},
        json={"social_links": {"instagram": "not-a-valid-url"}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_user_invalid_social_media_platform(
    async_client: AsyncClient, guest_token1: str
):
    token = guest_token1
    response = await async_client.patch(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": token},
        json={"social_links": {"myspace": "https://myspace.com/myprofile"}},
    )
    assert response.status_code == 422


@pytest.fixture
async def guest_token2(async_client: AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/guest")
    return response.cookies.get("cardie_session")


@pytest.mark.asyncio
async def test_get_user_deck_by_slug_public(
    async_client: AsyncClient, guest_token1: str
):
    # Get user profile to get username
    me_resp = await async_client.get(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": guest_token1},
    )
    username = me_resp.json()["username"]

    # Create a public deck
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Public Deck", "slug": "public-deck", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    deck_slug = deck_resp.json()["slug"]

    # Retrieve deck by username and slug without auth
    response = await async_client.get(
        f"/api/v1/users/profile/{username}/decks/{deck_slug}"
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Public Deck"


@pytest.mark.asyncio
async def test_get_user_deck_by_slug_private_owner(
    async_client: AsyncClient, guest_token1: str
):
    # Get user profile to get username
    me_resp = await async_client.get(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": guest_token1},
    )
    username = me_resp.json()["username"]

    # Create a private deck
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Private Deck", "slug": "private-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token1},
    )
    deck_slug = deck_resp.json()["slug"]

    # Retrieve deck by username and slug with owner's token
    response = await async_client.get(
        f"/api/v1/users/profile/{username}/decks/{deck_slug}",
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Private Deck"


@pytest.mark.asyncio
async def test_get_user_deck_by_slug_private_other(
    async_client: AsyncClient, guest_token1: str, guest_token2: str
):
    # Get user profile to get username
    me_resp = await async_client.get(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": guest_token1},
    )
    username = me_resp.json()["username"]

    # Create a private deck
    import uuid

    slug_rand = uuid.uuid4().hex[:8]
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Private Deck Other",
            "slug": f"private-deck-{slug_rand}",
            "privacy": "private",
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    deck_slug = deck_resp.json()["slug"]

    # Retrieve deck without auth
    resp_unauth = await async_client.get(
        f"/api/v1/users/profile/{username}/decks/{deck_slug}"
    )
    assert resp_unauth.status_code == 403

    # Retrieve deck with different user's auth
    resp_other = await async_client.get(
        f"/api/v1/users/profile/{username}/decks/{deck_slug}",
        headers={"X-Test-Cookie": guest_token2},
    )
    assert resp_other.status_code == 403


@pytest.mark.asyncio
async def test_get_user_deck_by_slug_not_found(
    async_client: AsyncClient, guest_token1: str
):
    me_resp = await async_client.get(
        "/api/v1/users/me",
        headers={"X-Test-Cookie": guest_token1},
    )
    username = me_resp.json()["username"]

    response = await async_client.get(
        f"/api/v1/users/profile/{username}/decks/non-existent-slug"
    )
    assert response.status_code == 404
