from unittest.mock import patch

import pytest
from httpx import AsyncClient

from src.auth.user_manager import UserManager


@pytest.fixture
async def registered_user(async_client: AsyncClient):
    email = "itemstest@example.com"
    password = "supersecretpassword"

    captured_token = None

    async def mock_on_after_request_verify(self, user, token, request=None):
        nonlocal captured_token
        captured_token = token

    with patch.object(
        UserManager, "on_after_request_verify", new=mock_on_after_request_verify
    ):
        reg_resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "is_guest": False,
            },
        )
        user_id = reg_resp.json()["id"]

        # Verify user
        await async_client.post("/api/v1/auth/verify", json={"token": captured_token})

    # Login
    login_resp = await async_client.post(
        "/api/v1/auth/jwt/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_resp.json()["access_token"]
    return {"id": user_id, "token": token}


@pytest.fixture
async def guest_token(async_client: AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/guest")
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_get_folder_items(
    async_client: AsyncClient, registered_user: dict, guest_token: str
):
    token = registered_user["token"]

    # Create parent folder
    folder_resp = await async_client.post(
        "/api/v1/folders/",
        json={"name": "Parent Folder", "slug": "parent-folder", "privacy": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert folder_resp.status_code == 200
    folder_id = folder_resp.json()["id"]

    # Create a child folder inside parent
    child_folder_resp = await async_client.post(
        "/api/v1/folders/",
        json={
            "name": "Child Folder",
            "slug": "child-folder",
            "privacy": "public",
            "parent_id": folder_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert child_folder_resp.status_code == 200

    # Create a deck inside parent
    deck_resp = await async_client.post(
        "/api/v1/decks/",
        json={
            "name": "Deck in Folder",
            "slug": "deck-in-folder",
            "privacy": "public",
            "folder_id": folder_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deck_resp.status_code == 200

    # Create an unlisted deck inside parent
    unlisted_deck_resp = await async_client.post(
        "/api/v1/decks/",
        json={
            "name": "Unlisted Deck",
            "slug": "unlisted-deck",
            "privacy": "unlisted",
            "folder_id": folder_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unlisted_deck_resp.status_code == 200

    # Create a private deck inside child folder
    private_deck_resp = await async_client.post(
        "/api/v1/decks/",
        json={
            "name": "Private Deck",
            "slug": "private-deck",
            "privacy": "private",
            "folder_id": child_folder_resp.json()["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert private_deck_resp.status_code == 200

    # Retrieve folder items for owner
    get_resp = await async_client.get(
        f"/api/v1/folders/{folder_id}/items",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert isinstance(data, list)
    assert len(data) == 4  # child folder, deck, unlisted deck, private deck (nested)

    child_folder_item = next(item for item in data if item["name"] == "Child Folder")
    assert child_folder_item["type"] == "folder"

    deck_item = next(item for item in data if item["name"] == "Deck in Folder")
    assert deck_item["type"] == "deck"

    # Retrieve folder items for guest (another user)
    get_resp_guest = await async_client.get(
        f"/api/v1/folders/{folder_id}/items",
        headers={"Authorization": f"Bearer {guest_token}"},
    )
    assert get_resp_guest.status_code == 200
    data_guest = get_resp_guest.json()
    assert isinstance(data_guest, list)
    assert len(data_guest) == 3  # child folder, deck, unlisted deck
    names = [item["name"] for item in data_guest]
    assert "Private Deck" not in names


@pytest.mark.asyncio
async def test_get_user_items(async_client: AsyncClient, registered_user: dict):
    token = registered_user["token"]
    user_id = registered_user["id"]

    # Create a folder
    folder_resp = await async_client.post(
        "/api/v1/folders/",
        json={"name": "User Folder", "slug": "user-folder", "privacy": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Create a deck
    deck_resp = await async_client.post(
        "/api/v1/decks/",
        json={"name": "User Deck", "slug": "user-deck", "privacy": "private"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Retrieve user items
    get_resp = await async_client.get(
        f"/api/v1/users/{user_id}/items",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert get_resp.status_code == 200
    data = get_resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    names = [item["name"] for item in data]
    assert "User Folder" in names
    assert "User Deck" in names

    folder_item = next(item for item in data if item["name"] == "User Folder")
    assert folder_item["type"] == "folder"
    deck_item = next(item for item in data if item["name"] == "User Deck")
    assert deck_item["type"] == "deck"


@pytest.mark.asyncio
async def test_items_properties(async_client: AsyncClient, registered_user: dict):
    token = registered_user["token"]
    user_id = registered_user["id"]

    # Create a folder with properties
    folder_resp = await async_client.post(
        "/api/v1/folders/",
        json={
            "name": "Folder Props",
            "slug": "folder-props",
            "privacy": "public",
            "properties": {"color": "#111111"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    folder_id = folder_resp.json()["id"]

    # Create a deck with properties inside the folder
    deck_resp = await async_client.post(
        "/api/v1/decks/",
        json={
            "name": "Deck Props",
            "slug": "deck-props",
            "privacy": "private",
            "folder_id": folder_id,
            "properties": {"color": "#222222"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    # Retrieve folder items
    get_folder_items = await async_client.get(
        f"/api/v1/folders/{folder_id}/items",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_folder_items.status_code == 200
    folder_items = get_folder_items.json()
    deck_item = next(item for item in folder_items if item["name"] == "Deck Props")
    assert deck_item.get("properties") == {"color": "#222222"}

    # Retrieve user items
    get_user_items = await async_client.get(
        f"/api/v1/users/{user_id}/items",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_user_items.status_code == 200
    user_items = get_user_items.json()
    folder_item = next(item for item in user_items if item["name"] == "Folder Props")
    assert folder_item.get("properties") == {"color": "#111111"}
    deck_user_item = next(item for item in user_items if item["name"] == "Deck Props")
    assert deck_user_item.get("properties") == {"color": "#222222"}
