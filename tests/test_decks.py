import pytest
from httpx import AsyncClient


@pytest.fixture
async def guest_token(async_client: AsyncClient) -> str:
    response = await async_client.post("/auth/guest")
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_create_deck(async_client: AsyncClient, guest_token: str):
    response = await async_client.post(
        "/decks/",
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
        "/decks/",
        json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )

    # Read decks
    response = await async_client.get(
        "/decks/", headers={"Authorization": f"Bearer {guest_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Deck"


@pytest.mark.asyncio
async def test_unauthorized_deck_creation(async_client: AsyncClient):
    response = await async_client.post(
        "/decks/", json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"}
    )

    # Should be 401 Unauthorized because no token was passed
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_deck_non_unique_slug(async_client: AsyncClient, guest_token: str):
    await async_client.post(
        "/decks/",
        json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )

    response = await async_client.post(
        "/decks/",
        json={"name": "Another Deck", "slug": "test-deck", "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Deck with this slug already exists"}
