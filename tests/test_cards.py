import pytest
from httpx import AsyncClient


@pytest.fixture
async def guest_token1(async_client: AsyncClient) -> str:
    response = await async_client.post("/v1/auth/guest")
    return response.json()["access_token"]


@pytest.fixture
async def guest_token2(async_client: AsyncClient) -> str:
    response = await async_client.post("/v1/auth/guest")
    return response.json()["access_token"]


@pytest.fixture
async def private_deck_id(async_client: AsyncClient, guest_token1: str) -> int:
    response = await async_client.post(
        "/v1/decks/",
        json={"name": "Private Deck", "slug": "private-deck", "privacy": "private"},
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    return response.json()["id"]


@pytest.fixture
async def public_deck_id(async_client: AsyncClient, guest_token1: str) -> int:
    response = await async_client.post(
        "/v1/decks/",
        json={"name": "Public Deck", "slug": "public-deck", "privacy": "public"},
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_card_owner_success(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    response = await async_client.post(
        f"/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["deck_id"] == private_deck_id
    assert "id" in data


@pytest.mark.asyncio
async def test_create_card_non_owner_forbidden(
    async_client: AsyncClient, guest_token2: str, private_deck_id: int
):
    response = await async_client.post(
        f"/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"Authorization": f"Bearer {guest_token2}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_card_non_existent_deck(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/v1/decks/999/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_read_cards_owner_success(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    # Create a card first
    await async_client.post(
        f"/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )

    response = await async_client.get(
        f"/v1/decks/{private_deck_id}/cards/",
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_read_cards_non_owner_forbidden_private_deck(
    async_client: AsyncClient, guest_token2: str, private_deck_id: int
):
    response = await async_client.get(
        f"/v1/decks/{private_deck_id}/cards/",
        headers={"Authorization": f"Bearer {guest_token2}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_read_cards_non_owner_success_public_deck(
    async_client: AsyncClient, guest_token2: str, public_deck_id: int
):
    response = await async_client.get(
        f"/v1/decks/{public_deck_id}/cards/",
        headers={"Authorization": f"Bearer {guest_token2}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_read_cards_non_existent_deck(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.get(
        "/v1/decks/999/cards/",
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code == 404
