import pytest
from httpx import AsyncClient


@pytest.fixture
async def guest_token(async_client: AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/guest")
    return response.cookies.get("cardie_session")


@pytest.fixture
async def guest_token2(async_client: AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/guest")
    return response.cookies.get("cardie_session")


@pytest.mark.asyncio
async def test_create_deck(async_client: AsyncClient, guest_token: str):
    response = await async_client.post(
        "/api/v1/decks",
        json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Deck"
    assert data["slug"] == "test-deck"
    assert "id" in data


@pytest.mark.asyncio
async def test_unauthorized_deck_creation(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/decks",
        json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"},
    )

    # Should be 401 Unauthorized because no token was passed
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_deck_non_unique_slug(async_client: AsyncClient, guest_token: str):
    await async_client.post(
        "/api/v1/decks",
        json={"name": "Test Deck", "slug": "test-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )

    response = await async_client.post(
        "/api/v1/decks",
        json={"name": "Another Deck", "slug": "test-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Deck with this slug already exists"}


@pytest.mark.asyncio
async def test_create_deck_name_too_long(async_client: AsyncClient, guest_token: str):
    response = await async_client.post(
        "/api/v1/decks",
        json={"name": "A" * 81, "slug": "valid-slug", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
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
        "/api/v1/decks",
        json={"name": "Valid Name", "slug": invalid_slug, "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_deck_invalid_privacy(async_client: AsyncClient, guest_token: str):
    response = await async_client.post(
        "/api/v1/decks",
        json={"name": "Valid Name", "slug": "valid-slug", "privacy": "super-secret"},
        headers={"X-Test-Cookie": guest_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_deck_non_existent_folder(
    async_client: AsyncClient, guest_token: str
):
    response = await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Valid Name",
            "slug": "valid-slug",
            "privacy": "private",
            "folder_id": "00000000-0000-0000-0000-000000999999",
        },
        headers={"X-Test-Cookie": guest_token},
    )
    assert response.status_code in (422, 404)


@pytest.mark.asyncio
async def test_create_deck_not_owned_folder(
    async_client: AsyncClient, guest_token: str, guest_token2: str
):
    # Create folder with guest_token2
    folder_resp = await async_client.post(
        "/api/v1/folders/",
        json={
            "name": "Other User Folder",
            "slug": "other-user-folder",
            "privacy": "private",
        },
        headers={"X-Test-Cookie": guest_token2},
    )
    folder_id = folder_resp.json()["id"]

    # Try to create deck in that folder with guest_token
    response = await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Valid Name",
            "slug": "valid-slug",
            "privacy": "private",
            "folder_id": folder_id,
        },
        headers={"X-Test-Cookie": guest_token},
    )
    assert response.status_code in (403, 404, 422)


@pytest.mark.asyncio
async def test_delete_deck(async_client: AsyncClient, guest_token: str):
    # Create deck
    create_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Deck to Delete", "slug": "deck-to-delete", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = create_resp.json()["id"]

    # Delete deck
    delete_resp = await async_client.delete(
        f"/api/v1/decks/{deck_id}",
        headers={"X-Test-Cookie": guest_token},
    )
    assert delete_resp.status_code == 204

    # Verify deck is deleted
    get_resp = await async_client.get(
        f"/api/v1/decks/{deck_id}",
        headers={"X-Test-Cookie": guest_token},
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_deck_not_owned(
    async_client: AsyncClient, guest_token: str, guest_token2: str
):
    # Create deck with guest_token
    create_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "User 1 Deck", "slug": "user-1-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = create_resp.json()["id"]

    # Try to delete deck with guest_token2
    delete_resp = await async_client.delete(
        f"/api/v1/decks/{deck_id}",
        headers={"X-Test-Cookie": guest_token2},
    )
    assert delete_resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_delete_deck_not_found(async_client: AsyncClient, guest_token: str):
    delete_resp = await async_client.delete(
        "/api/v1/decks/00000000-0000-0000-0000-000000999999",
        headers={"X-Test-Cookie": guest_token},
    )
    assert delete_resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_deck(async_client: AsyncClient, guest_token: str):
    # Create deck
    create_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Original Deck", "slug": "original-deck", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = create_resp.json()["id"]

    # Patch deck
    patch_resp = await async_client.patch(
        f"/api/v1/decks/{deck_id}",
        json={"name": "Patched Deck", "slug": "patched-deck", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["name"] == "Patched Deck"
    assert data["slug"] == "patched-deck"
    assert data["privacy"] == "public"


@pytest.mark.asyncio
async def test_patch_deck_not_owned(
    async_client: AsyncClient, guest_token: str, guest_token2: str
):
    # Create deck with guest_token
    create_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "User 1 Deck", "slug": "user-1-deck-patch", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = create_resp.json()["id"]

    # Try to patch deck with guest_token2
    patch_resp = await async_client.patch(
        f"/api/v1/decks/{deck_id}",
        json={"name": "Hacked Deck"},
        headers={"X-Test-Cookie": guest_token2},
    )
    assert patch_resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_patch_deck_not_found(async_client: AsyncClient, guest_token: str):
    patch_resp = await async_client.patch(
        "/api/v1/decks/00000000-0000-0000-0000-000000999999",
        json={"name": "Ghost Deck"},
        headers={"X-Test-Cookie": guest_token},
    )
    assert patch_resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_deck_folder_id(async_client: AsyncClient, guest_token: str):
    # Create folder
    folder_resp = await async_client.post(
        "/api/v1/folders/",
        json={"name": "Folder 1", "slug": "folder-1", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    folder_id = folder_resp.json()["id"]

    # Create deck
    create_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Deck 1", "slug": "deck-1-folder", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = create_resp.json()["id"]

    # Patch deck folder
    patch_resp = await async_client.patch(
        f"/api/v1/decks/{deck_id}",
        json={"folder_id": folder_id},
        headers={"X-Test-Cookie": guest_token},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["folder_id"] == folder_id


@pytest.mark.asyncio
async def test_patch_deck_non_unique_slug(async_client: AsyncClient, guest_token: str):
    # Create deck 1
    await async_client.post(
        "/api/v1/decks",
        json={"name": "Deck A", "slug": "deck-a", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )

    # Create deck 2
    create_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Deck B", "slug": "deck-b", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck2_id = create_resp.json()["id"]

    # Patch deck 2 with deck A's slug
    patch_resp = await async_client.patch(
        f"/api/v1/decks/{deck2_id}",
        json={"slug": "deck-a"},
        headers={"X-Test-Cookie": guest_token},
    )
    assert patch_resp.status_code == 400


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
async def test_patch_deck_invalid_slug(
    async_client: AsyncClient, guest_token: str, invalid_slug: str
):
    # Create deck
    create_resp = await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Valid Name",
            "slug": "valid-slug-for-patch",
            "privacy": "private",
        },
        headers={"X-Test-Cookie": guest_token},
    )

    # We might fail to create if the slug is taken from previous tests, let's use a unique slug just in case
    import uuid

    unique_slug = f"valid-slug-{uuid.uuid4().hex[:8]}"
    if create_resp.status_code != 200:
        create_resp = await async_client.post(
            "/api/v1/decks",
            json={"name": "Valid Name", "slug": unique_slug, "privacy": "private"},
            headers={"X-Test-Cookie": guest_token},
        )

    deck_id = create_resp.json()["id"]

    # Patch with invalid slug
    patch_resp = await async_client.patch(
        f"/api/v1/decks/{deck_id}",
        json={"slug": invalid_slug},
        headers={"X-Test-Cookie": guest_token},
    )
    assert patch_resp.status_code == 422


@pytest.mark.asyncio
async def test_delete_deck_cascades_cards(
    async_client: AsyncClient, guest_token: str, async_session
):
    import uuid

    from src import models

    unique_slug = f"deck-with-cards-{uuid.uuid4().hex[:8]}"

    # Create deck
    create_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Deck with Cards", "slug": unique_slug, "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    deck_id = create_resp.json()["id"]

    # Create a card in the deck
    card_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={
            "front": [{"type": "text", "content": "front"}],
            "back": [{"type": "text", "content": "back"}],
        },
        headers={"X-Test-Cookie": guest_token},
    )
    card_id = card_resp.json()["id"]

    # Delete the deck
    delete_resp = await async_client.delete(
        f"/api/v1/decks/{deck_id}",
        headers={"X-Test-Cookie": guest_token},
    )
    assert delete_resp.status_code == 204

    # Verify the card is also deleted from the database
    card = await async_session.get(models.Card, uuid.UUID(card_id))
    assert card is None


@pytest.mark.asyncio
async def test_create_deck_with_properties(async_client: AsyncClient, guest_token: str):
    response = await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Deck Properties",
            "slug": "deck-properties",
            "privacy": "private",
            "properties": {"color": "#ffffff"},
        },
        headers={"X-Test-Cookie": guest_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("properties") == {"color": "#ffffff"}

    # Also test retrieve
    get_resp = await async_client.get(
        f"/api/v1/decks/{data['id']}",
        headers={"X-Test-Cookie": guest_token},
    )
    assert get_resp.status_code == 200
    assert get_resp.json().get("properties") == {"color": "#ffffff"}


@pytest.mark.asyncio
async def test_create_deck_empty_properties(
    async_client: AsyncClient, guest_token: str
):
    response = await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Deck Empty Prop",
            "slug": "deck-empty-prop",
            "privacy": "private",
        },
        headers={"X-Test-Cookie": guest_token},
    )
    assert response.status_code == 200
    assert "properties" not in response.json() or response.json()["properties"] in (
        None,
        {},
    )


@pytest.mark.asyncio
async def test_create_deck_invalid_properties(
    async_client: AsyncClient, guest_token: str
):
    # invalid color type
    response1 = await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Deck Inv Prop",
            "slug": "deck-inv-prop1",
            "privacy": "private",
            "properties": {"color": 123},
        },
        headers={"X-Test-Cookie": guest_token},
    )
    assert response1.status_code == 422

    # invalid property key
    response2 = await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Deck Inv Prop 2",
            "slug": "deck-inv-prop2",
            "privacy": "private",
            "properties": {"invalid_prop": "test"},
        },
        headers={"X-Test-Cookie": guest_token},
    )
    assert response2.status_code == 422
