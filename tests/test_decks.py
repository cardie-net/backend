import pytest
from httpx import AsyncClient


@pytest.fixture
async def guest_token(async_client: AsyncClient) -> str:
    response = await async_client.post("/v1/auth/guest")
    return response.json()["access_token"]


@pytest.fixture
async def guest_token2(async_client: AsyncClient) -> str:
    response = await async_client.post("/v1/auth/guest")
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_create_deck(async_client: AsyncClient, guest_token: str):
    response = await async_client.post(
        "/v1/decks/",
        json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Deck"
    assert data["slug"] == "test-deck"
    assert "id" in data


@pytest.mark.asyncio
async def test_read_decks(async_client: AsyncClient, guest_token: str):
    # Create deck first
    await async_client.post(
        "/v1/decks/",
        json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )

    # Read decks
    response = await async_client.get(
        "/v1/decks/", headers={"Authorization": f"Bearer {guest_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Deck"


@pytest.mark.asyncio
async def test_unauthorized_deck_creation(async_client: AsyncClient):
    response = await async_client.post(
        "/v1/decks/",
        json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"},
    )

    # Should be 401 Unauthorized because no token was passed
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_deck_non_unique_slug(async_client: AsyncClient, guest_token: str):
    await async_client.post(
        "/v1/decks/",
        json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )

    response = await async_client.post(
        "/v1/decks/",
        json={"name": "Another Deck", "slug": "test-deck", "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Deck with this slug already exists"}


@pytest.mark.asyncio
async def test_create_deck_name_too_long(async_client: AsyncClient, guest_token: str):
    response = await async_client.post(
        "/v1/decks/",
        json={"name": "A" * 81, "slug": "valid-slug", "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "invalid_slug",
    [
        "invalid slug",
        "invalid/slug",
        "invalid#slug",
        "invalid?slug",
        "invalid&slug",
        "invalid%slug",
        "invalid\\slug",
        "invalid@slug",
        "invalid:slug",
        "",
        "A" * 81,
    ],
)
@pytest.mark.asyncio
async def test_create_deck_invalid_slug(
    async_client: AsyncClient, guest_token: str, invalid_slug: str
):
    response = await async_client.post(
        "/v1/decks/",
        json={"name": "Valid Name", "slug": invalid_slug, "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_deck_invalid_privacy(async_client: AsyncClient, guest_token: str):
    response = await async_client.post(
        "/v1/decks/",
        json={"name": "Valid Name", "slug": "valid-slug", "privacy": "super-secret"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_deck_non_existent_folder(
    async_client: AsyncClient, guest_token: str
):
    response = await async_client.post(
        "/v1/decks/",
        json={
            "name": "Valid Name",
            "slug": "valid-slug",
            "privacy": "private",
            "folder_id": 999999,
        },
        headers={"Authorization": f"Bearer {guest_token}"},
    )
    assert response.status_code in (422, 404)


@pytest.mark.asyncio
async def test_create_deck_not_owned_folder(
    async_client: AsyncClient, guest_token: str, guest_token2: str
):
    # Create folder with guest_token2
    folder_resp = await async_client.post(
        "/v1/folders/",
        json={
            "name": "Other User Folder",
            "slug": "other-user-folder",
            "privacy": "private",
        },
        headers={"Authorization": f"Bearer {guest_token2}"},
    )
    folder_id = folder_resp.json()["id"]

    # Try to create deck in that folder with guest_token
    response = await async_client.post(
        "/v1/decks/",
        json={
            "name": "Valid Name",
            "slug": "valid-slug",
            "privacy": "private",
            "folder_id": folder_id,
        },
        headers={"Authorization": f"Bearer {guest_token}"},
    )
    assert response.status_code in (403, 404, 422)
