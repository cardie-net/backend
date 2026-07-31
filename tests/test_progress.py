import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_progress_owner_success(async_client: AsyncClient, guest_token: str):
    # 1. Create a deck
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Progress Deck", "slug": "progress-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = deck_resp.json()["id"]

    # 2. Create cards
    card1_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={
            "front": [{"type": "text", "content": "Q1"}],
            "back": [{"type": "text", "content": "A1"}],
        },
        headers={"X-Test-Cookie": guest_token},
    )
    card1_id = card1_resp.json()["id"]

    card2_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={
            "front": [{"type": "text", "content": "Q2"}],
            "back": [{"type": "text", "content": "A2"}],
        },
        headers={"X-Test-Cookie": guest_token},
    )
    card2_id = card2_resp.json()["id"]

    # 3. Get progress (should be empty)
    prog_get = await async_client.get(
        f"/api/v1/decks/{deck_id}/progress",
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_get.status_code == 200
    assert prog_get.json() == []

    # 4. Sync progress (Box 2 for Card 1, Box 3 for Card 2)
    prog_post = await async_client.post(
        f"/api/v1/decks/{deck_id}/progress",
        json={
            "progress": [
                {"card_id": card1_id, "box": 2},
                {"card_id": card2_id, "box": 3},
            ]
        },
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_post.status_code == 204

    # 5. Get progress (should reflect updates)
    prog_get2 = await async_client.get(
        f"/api/v1/decks/{deck_id}/progress",
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_get2.status_code == 200
    data = prog_get2.json()
    assert len(data) == 2
    # Verify contents
    prog_map = {item["card_id"]: item["box"] for item in data}
    assert prog_map[card1_id] == 2
    assert prog_map[card2_id] == 3

    # 6. Drop Card 1 back to Box 1
    prog_post2 = await async_client.post(
        f"/api/v1/decks/{deck_id}/progress",
        json={"progress": [{"card_id": card1_id, "box": 1}]},
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_post2.status_code == 204

    prog_get3 = await async_client.get(
        f"/api/v1/decks/{deck_id}/progress",
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_get3.status_code == 200
    data3 = prog_get3.json()
    assert len(data3) == 1
    assert data3[0]["card_id"] == card2_id


@pytest.mark.asyncio
async def test_progress_public_other_user(
    async_client: AsyncClient, guest_token: str, guest_token2: str
):
    # User 1 creates public deck
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Public Deck", "slug": "public-deck", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = deck_resp.json()["id"]

    card_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={
            "front": [{"type": "text", "content": "Q1"}],
            "back": [{"type": "text", "content": "A1"}],
        },
        headers={"X-Test-Cookie": guest_token},
    )
    card_id = card_resp.json()["id"]

    # User 2 syncs progress
    prog_post = await async_client.post(
        f"/api/v1/decks/{deck_id}/progress",
        json={"progress": [{"card_id": card_id, "box": 2}]},
        headers={"X-Test-Cookie": guest_token2},
    )
    assert prog_post.status_code == 204

    # User 2 gets progress
    prog_get = await async_client.get(
        f"/api/v1/decks/{deck_id}/progress",
        headers={"X-Test-Cookie": guest_token2},
    )
    assert prog_get.status_code == 200
    assert len(prog_get.json()) == 1
    assert prog_get.json()[0]["box"] == 2

    # User 1 gets progress (should be empty for them)
    prog_get_user1 = await async_client.get(
        f"/api/v1/decks/{deck_id}/progress",
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_get_user1.status_code == 200
    assert len(prog_get_user1.json()) == 0


@pytest.mark.asyncio
async def test_progress_private_other_user(
    async_client: AsyncClient, guest_token: str, guest_token2: str
):
    # User 1 creates private deck
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Private Deck", "slug": "private-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = deck_resp.json()["id"]

    card_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={
            "front": [{"type": "text", "content": "Q1"}],
            "back": [{"type": "text", "content": "A1"}],
        },
        headers={"X-Test-Cookie": guest_token},
    )
    card_id = card_resp.json()["id"]

    # User 2 tries to sync progress
    prog_post = await async_client.post(
        f"/api/v1/decks/{deck_id}/progress",
        json={"progress": [{"card_id": card_id, "box": 2}]},
        headers={"X-Test-Cookie": guest_token2},
    )
    assert prog_post.status_code == 403

    # User 2 tries to get progress
    prog_get = await async_client.get(
        f"/api/v1/decks/{deck_id}/progress",
        headers={"X-Test-Cookie": guest_token2},
    )
    assert prog_get.status_code == 403


@pytest.mark.asyncio
async def test_progress_invalid_deck(async_client: AsyncClient, guest_token: str):
    fake_deck_id = str(uuid.uuid4())

    prog_post = await async_client.post(
        f"/api/v1/decks/{fake_deck_id}/progress",
        json={"progress": [{"card_id": str(uuid.uuid4()), "box": 2}]},
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_post.status_code == 404

    prog_get = await async_client.get(
        f"/api/v1/decks/{fake_deck_id}/progress",
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_get.status_code == 404


@pytest.mark.asyncio
async def test_progress_invalid_card_data(async_client: AsyncClient, guest_token: str):
    # Create deck
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Deck", "slug": "deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = deck_resp.json()["id"]

    # Try syncing with invalid card id format
    prog_post = await async_client.post(
        f"/api/v1/decks/{deck_id}/progress",
        json={"progress": [{"card_id": "not-a-uuid", "box": 2}]},
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_post.status_code == 422  # Validation Error

    # Try syncing with valid card id format but fake ID
    fake_card_id = str(uuid.uuid4())
    prog_post2 = await async_client.post(
        f"/api/v1/decks/{deck_id}/progress",
        json={"progress": [{"card_id": fake_card_id, "box": 2}]},
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_post2.status_code == 204

    # Fake ID should be silently ignored by backend filtering
    prog_get = await async_client.get(
        f"/api/v1/decks/{deck_id}/progress",
        headers={"X-Test-Cookie": guest_token},
    )
    assert prog_get.status_code == 200
    assert len(prog_get.json()) == 0
