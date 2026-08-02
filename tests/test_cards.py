import pytest
from httpx import AsyncClient


@pytest.fixture
async def private_deck_id(async_client: AsyncClient, guest_token1: str) -> int:
    response = await async_client.post(
        "/api/v1/decks/",
        json={"name": "Private Deck", "slug": "private-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token1},
    )
    return response.json()["id"]


@pytest.fixture
async def public_deck_id(async_client: AsyncClient, guest_token1: str) -> int:
    response = await async_client.post(
        "/api/v1/decks/",
        json={"name": "Public Deck", "slug": "public-deck", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_card_owner_success(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    response = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
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
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token2},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_card_non_existent_deck(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000999/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_read_cards_owner_success(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    # Create a card first
    await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )

    response = await async_client.get(
        f"/api/v1/decks/{private_deck_id}/cards/",
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_read_cards_non_owner_forbidden_private_deck(
    async_client: AsyncClient, guest_token2: str, private_deck_id: int
):
    response = await async_client.get(
        f"/api/v1/decks/{private_deck_id}/cards/",
        headers={"X-Test-Cookie": guest_token2},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_read_cards_non_owner_success_public_deck(
    async_client: AsyncClient, guest_token2: str, public_deck_id: int
):
    response = await async_client.get(
        f"/api/v1/decks/{public_deck_id}/cards/",
        headers={"X-Test-Cookie": guest_token2},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_read_cards_non_existent_deck(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.get(
        "/api/v1/decks/00000000-0000-0000-0000-000000000999/cards/",
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_card_invalid_front_data(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    response = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": "this should be a list",
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_card_invalid_back_data(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    response = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": "this should be a list",
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_card_missing_fields(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    response = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_card_owner_success(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    # First create a card
    create_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    card_id = create_resp.json()["id"]

    # Delete the card
    del_resp = await async_client.delete(
        f"/api/v1/decks/{private_deck_id}/cards/{card_id}",
        headers={"X-Test-Cookie": guest_token1},
    )
    assert del_resp.status_code == 204

    # Verify it's deleted
    get_resp = await async_client.get(
        f"/api/v1/decks/{private_deck_id}/cards/",
        headers={"X-Test-Cookie": guest_token1},
    )
    assert len(get_resp.json()) == 0


@pytest.mark.asyncio
async def test_delete_card_non_owner_forbidden(
    async_client: AsyncClient,
    guest_token1: str,
    guest_token2: str,
    private_deck_id: int,
):
    create_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Front"}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    card_id = create_resp.json()["id"]

    del_resp = await async_client.delete(
        f"/api/v1/decks/{private_deck_id}/cards/{card_id}",
        headers={"X-Test-Cookie": guest_token2},
    )
    assert del_resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_card_owner_success(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    create_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Old Front"}],
            "back": [{"type": "text", "content": "Old Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    card_id = create_resp.json()["id"]

    patch_resp = await async_client.patch(
        f"/api/v1/decks/{private_deck_id}/cards/{card_id}",
        json={
            "front": [{"type": "text", "content": "New Front"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["front"][0]["content"] == "New Front"
    assert data["back"][0]["content"] == "Old Back"


@pytest.mark.asyncio
async def test_patch_card_non_owner_forbidden(
    async_client: AsyncClient,
    guest_token1: str,
    guest_token2: str,
    private_deck_id: int,
):
    create_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "Old Front"}],
            "back": [{"type": "text", "content": "Old Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    card_id = create_resp.json()["id"]

    patch_resp = await async_client.patch(
        f"/api/v1/decks/{private_deck_id}/cards/{card_id}",
        json={
            "front": [{"type": "text", "content": "New Front"}],
        },
        headers={"X-Test-Cookie": guest_token2},
    )
    assert patch_resp.status_code == 403


@pytest.mark.asyncio
async def test_reorder_cards_owner_success(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    # Create two cards
    c1 = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "1"}],
            "back": [{"type": "text", "content": "1"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    c2 = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "2"}],
            "back": [{"type": "text", "content": "2"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    id1 = c1.json()["id"]
    id2 = c2.json()["id"]

    # Reorder them
    reorder_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/reorder",
        json={"card_ids": [id2, id1]},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert reorder_resp.status_code == 200

    # Get cards, check order
    get_resp = await async_client.get(
        f"/api/v1/decks/{private_deck_id}/cards/",
        headers={"X-Test-Cookie": guest_token1},
    )
    cards = get_resp.json()
    assert len(cards) == 2
    assert cards[0]["id"] == id2
    assert cards[1]["id"] == id1


@pytest.mark.asyncio
async def test_reorder_cards_non_owner_forbidden(
    async_client: AsyncClient,
    guest_token1: str,
    guest_token2: str,
    private_deck_id: int,
):
    c1 = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "1"}],
            "back": [{"type": "text", "content": "1"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    id1 = c1.json()["id"]

    reorder_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/reorder",
        json={"card_ids": [id1]},
        headers={"X-Test-Cookie": guest_token2},
    )
    assert reorder_resp.status_code == 403


@pytest.mark.asyncio
async def test_reorder_cards_invalid_card_id(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    c1 = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "1"}],
            "back": [{"type": "text", "content": "1"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    id1 = c1.json()["id"]

    reorder_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/reorder",
        json={"card_ids": [id1, "00000000-0000-0000-0000-000000000999"]},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert reorder_resp.status_code == 400


@pytest.mark.asyncio
async def test_reorder_cards_subset(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    c1 = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "1"}],
            "back": [{"type": "text", "content": "1"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    c2 = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "2"}],
            "back": [{"type": "text", "content": "2"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    id1 = c1.json()["id"]

    reorder_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/reorder",
        json={"card_ids": [id1]},  # Missing c2
        headers={"X-Test-Cookie": guest_token1},
    )
    assert reorder_resp.status_code == 400


@pytest.mark.asyncio
async def test_reorder_cards_no_cards(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    # Deck has 1 card
    await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "1"}],
            "back": [{"type": "text", "content": "1"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )

    reorder_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/reorder",
        json={"card_ids": []},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert reorder_resp.status_code == 400


@pytest.mark.asyncio
async def test_reorder_cards_duplicate_id(
    async_client: AsyncClient, guest_token1: str, private_deck_id: int
):
    c1 = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "1"}],
            "back": [{"type": "text", "content": "1"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    id1 = c1.json()["id"]

    reorder_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/reorder",
        json={"card_ids": [id1, id1]},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert reorder_resp.status_code == 400


# --- Card image S3 cleanup ---


# --- Card image S3 cleanup ---


def _managed_url(user_id: str) -> str:
    return f"https://cdn.example.com/card-images/{user_id}/deck/c.webp"


@pytest.fixture
async def guest_user_id(async_client: AsyncClient, guest_token1: str) -> str:
    resp = await async_client.get(
        "/api/v1/users/me", headers={"X-Test-Cookie": guest_token1}
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_patch_card_removed_image_cleans_up_s3(
    async_client: AsyncClient,
    guest_token1: str,
    guest_user_id: str,
    private_deck_id: int,
):
    from unittest.mock import patch

    url = _managed_url(guest_user_id)
    create_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "image", "url": url}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    card_id = create_resp.json()["id"]

    with patch("src.routers.cards.delete_managed_images") as mock_del:
        patch_resp = await async_client.patch(
            f"/api/v1/decks/{private_deck_id}/cards/{card_id}",
            json={"front": [{"type": "text", "content": "New Front"}]},
            headers={"X-Test-Cookie": guest_token1},
        )
    assert patch_resp.status_code == 200
    mock_del.assert_called_once_with([url], f"card-images/{guest_user_id}/")


@pytest.mark.asyncio
async def test_patch_card_removed_other_users_image_not_deleted(
    async_client: AsyncClient,
    guest_token1: str,
    guest_user_id: str,
    private_deck_id: int,
):
    """A card referencing another user's managed URL must not delete it."""
    from unittest.mock import patch

    other_url = "https://cdn.example.com/card-images/other-user/deck/c.webp"
    create_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "image", "url": other_url}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    card_id = create_resp.json()["id"]

    with patch("src.routers.cards.delete_managed_images") as mock_del:
        del_resp = await async_client.delete(
            f"/api/v1/decks/{private_deck_id}/cards/{card_id}",
            headers={"X-Test-Cookie": guest_token1},
        )
    assert del_resp.status_code == 204
    mock_del.assert_called_once_with([other_url], f"card-images/{guest_user_id}/")


@pytest.mark.asyncio
async def test_patch_card_kept_image_no_cleanup(
    async_client: AsyncClient,
    guest_token1: str,
    guest_user_id: str,
    private_deck_id: int,
):
    from unittest.mock import patch

    url = _managed_url(guest_user_id)
    create_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "image", "url": url}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    card_id = create_resp.json()["id"]

    with patch("src.routers.cards.delete_managed_images") as mock_del:
        patch_resp = await async_client.patch(
            f"/api/v1/decks/{private_deck_id}/cards/{card_id}",
            json={
                "front": [
                    {"type": "image", "url": url},
                    {"type": "text", "content": "New"},
                ],
                "back": [{"type": "text", "content": "Back"}],
            },
            headers={"X-Test-Cookie": guest_token1},
        )
    assert patch_resp.status_code == 200
    assert mock_del.call_count == 0


@pytest.mark.asyncio
async def test_delete_card_cleans_up_image_s3(
    async_client: AsyncClient,
    guest_token1: str,
    guest_user_id: str,
    private_deck_id: int,
):
    from unittest.mock import patch

    url = _managed_url(guest_user_id)
    create_resp = await async_client.post(
        f"/api/v1/decks/{private_deck_id}/cards/",
        json={
            "front": [{"type": "image", "url": url}],
            "back": [{"type": "text", "content": "Back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    card_id = create_resp.json()["id"]

    with patch("src.routers.cards.delete_managed_images") as mock_del:
        del_resp = await async_client.delete(
            f"/api/v1/decks/{private_deck_id}/cards/{card_id}",
            headers={"X-Test-Cookie": guest_token1},
        )
    assert del_resp.status_code == 204
    mock_del.assert_called_once_with([url], f"card-images/{guest_user_id}/")
