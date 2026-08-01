import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_srs_counts_empty(async_client: AsyncClient, guest_token: str):
    response = await async_client.get(
        "/api/v1/srs/counts", headers={"X-Test-Cookie": guest_token}
    )
    assert response.status_code == 200
    assert response.json() == {}


@pytest.mark.asyncio
async def test_srs_flow(async_client: AsyncClient, guest_token: str):
    # 1. Create a deck
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "SRS Deck", "slug": "srs-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    assert deck_resp.status_code == 200
    deck_id = deck_resp.json()["id"]

    # 2. Create some cards
    card_ids = []
    for i in range(3):
        card_resp = await async_client.post(
            f"/api/v1/decks/{deck_id}/cards",
            json={
                "front": [{"type": "text", "content": f"Q{i}"}],
                "back": [{"type": "text", "content": f"A{i}"}],
            },
            headers={"X-Test-Cookie": guest_token},
        )
        assert card_resp.status_code == 200
        card_ids.append(card_resp.json()["id"])

    # 3. Check counts - should be 3 new
    counts_resp = await async_client.get(
        "/api/v1/srs/counts", headers={"X-Test-Cookie": guest_token}
    )
    assert counts_resp.status_code == 200
    counts = counts_resp.json()
    assert deck_id in counts
    assert counts[deck_id]["new_count"] == 3
    assert counts[deck_id]["learning_count"] == 0
    assert counts[deck_id]["review_count"] == 0

    # 4. Fetch study cards
    study_resp = await async_client.get(
        f"/api/v1/decks/{deck_id}/srs/study", headers={"X-Test-Cookie": guest_token}
    )
    assert study_resp.status_code == 200
    study_data = study_resp.json()
    assert len(study_data["new_cards"]) == 3
    assert len(study_data["learning_cards"]) == 0
    assert len(study_data["review_cards"]) == 0

    # 5. Submit reviews
    # Card 0 -> Again (0): becomes learning
    # Card 1 -> Good (2): reps=1, interval=1.0, due tomorrow (not learning, not review today)
    # Card 2 -> Easy (3): reps=1, interval=4.0, due in 4 days
    review_payload = {
        "reviews": [
            {"card_id": card_ids[0], "rating": 0},
            {"card_id": card_ids[1], "rating": 2},
            {"card_id": card_ids[2], "rating": 3},
        ]
    }
    review_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/srs/review",
        json=review_payload,
        headers={"X-Test-Cookie": guest_token},
    )
    assert review_resp.status_code == 204

    # 6. Check counts again
    counts_resp2 = await async_client.get(
        "/api/v1/srs/counts", headers={"X-Test-Cookie": guest_token}
    )
    counts2 = counts_resp2.json()[deck_id]
    assert counts2["new_count"] == 0
    assert counts2["learning_count"] == 0  # Card 0 has interval 1.0, due tomorrow
    assert counts2["review_count"] == 0  # Card 1 and 2 are due in the future

    # 7. Fetch study cards again
    study_resp2 = await async_client.get(
        f"/api/v1/decks/{deck_id}/srs/study", headers={"X-Test-Cookie": guest_token}
    )
    study_data2 = study_resp2.json()
    assert len(study_data2["new_cards"]) == 0
    assert len(study_data2["learning_cards"]) == 0
    assert len(study_data2["review_cards"]) == 0


@pytest.mark.asyncio
async def test_srs_limits(async_client: AsyncClient, guest_token: str):
    # Create deck
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Limits Deck", "slug": "limits-deck"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = deck_resp.json()["id"]

    # Create 15 cards (limit for new is 10)
    for i in range(15):
        await async_client.post(
            f"/api/v1/decks/{deck_id}/cards",
            json={
                "front": [{"type": "text", "content": f"Q{i}"}],
                "back": [{"type": "text", "content": f"A{i}"}],
            },
            headers={"X-Test-Cookie": guest_token},
        )

    # Check counts
    counts_resp = await async_client.get(
        "/api/v1/srs/counts", headers={"X-Test-Cookie": guest_token}
    )
    counts = counts_resp.json()[deck_id]
    assert counts["new_count"] == 10  # Capped at 10

    # Fetch study cards
    study_resp = await async_client.get(
        f"/api/v1/decks/{deck_id}/srs/study", headers={"X-Test-Cookie": guest_token}
    )
    study_data = study_resp.json()
    assert len(study_data["new_cards"]) == 10  # Capped at 10


@pytest.mark.asyncio
async def test_srs_permissions(
    async_client: AsyncClient, guest_token: str, guest_token2: str
):
    # User 1 creates deck
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "User1 Deck", "slug": "user1-deck", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = deck_resp.json()["id"]

    # User 2 tries to fetch study cards
    study_resp = await async_client.get(
        f"/api/v1/decks/{deck_id}/srs/study", headers={"X-Test-Cookie": guest_token2}
    )
    assert study_resp.status_code == 404  # Expected behavior from current srs router

    # User 2 tries to submit review
    review_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/srs/review",
        json={"reviews": []},
        headers={"X-Test-Cookie": guest_token2},
    )
    assert review_resp.status_code == 404

    # User 1 fetching should work
    study_resp_user1 = await async_client.get(
        f"/api/v1/decks/{deck_id}/srs/study", headers={"X-Test-Cookie": guest_token}
    )
    assert study_resp_user1.status_code == 200


@pytest.mark.asyncio
async def test_srs_invalid_deck_and_cards(async_client: AsyncClient, guest_token: str):
    fake_deck_id = str(uuid.uuid4())

    study_resp = await async_client.get(
        f"/api/v1/decks/{fake_deck_id}/srs/study",
        headers={"X-Test-Cookie": guest_token},
    )
    assert study_resp.status_code == 404

    review_resp = await async_client.post(
        f"/api/v1/decks/{fake_deck_id}/srs/review",
        json={"reviews": [{"card_id": str(uuid.uuid4()), "rating": 0}]},
        headers={"X-Test-Cookie": guest_token},
    )
    assert review_resp.status_code == 404

    # Now create real deck, but review fake cards
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Fake Cards Deck", "slug": "fake-cards"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = deck_resp.json()["id"]

    fake_card_id = str(uuid.uuid4())
    review_resp2 = await async_client.post(
        f"/api/v1/decks/{deck_id}/srs/review",
        json={"reviews": [{"card_id": fake_card_id, "rating": 2}]},
        headers={"X-Test-Cookie": guest_token},
    )
    assert review_resp2.status_code == 204
    # The backend handles fake cards silently by ignoring them in the query

    # It should not have crashed and getting counts should still work
    counts_resp = await async_client.get(
        "/api/v1/srs/counts", headers={"X-Test-Cookie": guest_token}
    )
    assert counts_resp.status_code == 200
    assert counts_resp.json()[deck_id]["new_count"] == 0
