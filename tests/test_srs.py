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

    # 3. Check counts - should be unactivated initially
    counts_resp = await async_client.get(
        "/api/v1/srs/counts", headers={"X-Test-Cookie": guest_token}
    )
    assert counts_resp.status_code == 200
    counts = counts_resp.json()
    assert deck_id in counts
    assert counts[deck_id]["activated"] is False
    assert counts[deck_id]["new_count"] == 0

    # 3.5. Activate SRS for deck
    act_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/srs/activate", headers={"X-Test-Cookie": guest_token}
    )
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert act_data["activated"] is True
    assert act_data["new_count"] == 3

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
    # Card 0 -> Again (0): stays in today's learning queue (short step, due today)
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
    assert counts2["activated"] is True
    assert counts2["new_count"] == 0
    # Card 0 was rated "again" -> still due today, so it shows as learning
    assert counts2["learning_count"] == 1
    assert counts2["review_count"] == 0  # Card 1 and 2 are due in the future

    # 7. Fetch study cards again
    study_resp2 = await async_client.get(
        f"/api/v1/decks/{deck_id}/srs/study", headers={"X-Test-Cookie": guest_token}
    )
    study_data2 = study_resp2.json()
    assert len(study_data2["new_cards"]) == 0
    # Regression: a card marked "again" must be re-asked the same day, even
    # if the user left the session before finishing (it lands in learning).
    assert len(study_data2["learning_cards"]) == 1
    assert study_data2["learning_cards"][0]["card_id"] == card_ids[0]
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

    # Activate SRS
    await async_client.post(
        f"/api/v1/decks/{deck_id}/srs/activate", headers={"X-Test-Cookie": guest_token}
    )

    # Check counts
    counts_resp = await async_client.get(
        "/api/v1/srs/counts", headers={"X-Test-Cookie": guest_token}
    )
    counts = counts_resp.json()[deck_id]
    assert counts["activated"] is True
    assert counts["new_count"] == 10  # Capped at 10

    # Fetch study cards
    study_resp = await async_client.get(
        f"/api/v1/decks/{deck_id}/srs/study", headers={"X-Test-Cookie": guest_token}
    )
    study_data = study_resp.json()
    assert len(study_data["new_cards"]) == 10  # Capped at 10


@pytest.mark.asyncio
async def test_srs_permissions(
    async_client: AsyncClient, user_token: str, guest_token: str
):
    # User 1 creates a public deck and a card
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "User1 Deck", "slug": "user1-deck", "privacy": "public"},
        headers={"X-Test-Cookie": user_token},
    )
    deck_id = deck_resp.json()["id"]

    card_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={
            "front": [{"type": "text", "content": "Question"}],
            "back": [{"type": "text", "content": "Answer"}],
        },
        headers={"X-Test-Cookie": user_token},
    )
    card_id = card_resp.json()["id"]

    # User 1 creates a private deck
    priv_deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "User1 Private Deck", "slug": "user1-priv", "privacy": "private"},
        headers={"X-Test-Cookie": user_token},
    )
    priv_deck_id = priv_deck_resp.json()["id"]

    # User 2 CAN activate SRS on User 1's public deck
    act_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/srs/activate", headers={"X-Test-Cookie": guest_token}
    )
    assert act_resp.status_code == 200
    assert act_resp.json()["activated"] is True
    assert act_resp.json()["new_count"] == 1

    # User 2 gets counts and sees the activated public deck
    counts_resp = await async_client.get(
        "/api/v1/srs/counts", headers={"X-Test-Cookie": guest_token}
    )
    assert counts_resp.status_code == 200
    assert deck_id in counts_resp.json()
    assert counts_resp.json()[deck_id]["activated"] is True

    # User 2 CAN fetch study cards on User 1's public deck
    study_resp = await async_client.get(
        f"/api/v1/decks/{deck_id}/srs/study", headers={"X-Test-Cookie": guest_token}
    )
    assert study_resp.status_code == 200
    assert len(study_resp.json()["new_cards"]) == 1

    # User 2 CAN submit reviews on User 1's public deck
    review_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/srs/review",
        json={"reviews": [{"card_id": card_id, "rating": 3}]},
        headers={"X-Test-Cookie": guest_token},
    )
    assert review_resp.status_code == 204

    # User 1's own SRS state is unaffected (unactivated, 0 progress)
    user1_counts = await async_client.get(
        "/api/v1/srs/counts", headers={"X-Test-Cookie": user_token}
    )
    assert user1_counts.status_code == 200
    assert user1_counts.json()[deck_id]["activated"] is False

    # User 2 CANNOT access User 1's private deck
    priv_study_resp = await async_client.get(
        f"/api/v1/decks/{priv_deck_id}/srs/study",
        headers={"X-Test-Cookie": guest_token},
    )
    assert priv_study_resp.status_code == 403

    priv_act_resp = await async_client.post(
        f"/api/v1/decks/{priv_deck_id}/srs/activate",
        headers={"X-Test-Cookie": guest_token},
    )
    assert priv_act_resp.status_code == 403

    priv_review_resp = await async_client.post(
        f"/api/v1/decks/{priv_deck_id}/srs/review",
        json={"reviews": []},
        headers={"X-Test-Cookie": guest_token},
    )
    assert priv_review_resp.status_code == 403


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
