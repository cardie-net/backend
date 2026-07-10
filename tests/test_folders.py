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


@pytest.mark.asyncio
async def test_create_folder(async_client: AsyncClient, guest_token1: str):
    response = await async_client.post(
        "/v1/folders/",
        json={"name": "Test Folder", "slug": "test-folder", "privacy": "public"},
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Folder"
    assert data["slug"] == "test-folder"
    assert data["privacy"] == "public"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_folder_contents(async_client: AsyncClient, guest_token1: str):
    # Create parent folder
    folder_resp = await async_client.post(
        "/v1/folders/",
        json={"name": "Parent Folder", "slug": "parent-folder", "privacy": "public"},
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert folder_resp.status_code == 200
    folder_id = folder_resp.json()["id"]

    # Create a child folder inside parent
    child_folder_resp = await async_client.post(
        "/v1/folders/",
        json={
            "name": "Child Folder",
            "slug": "child-folder",
            "privacy": "public",
            "parent_id": folder_id,
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert child_folder_resp.status_code == 200

    # Create a deck inside parent
    deck_resp = await async_client.post(
        "/v1/decks/",
        json={
            "name": "Deck in Folder",
            "slug": "deck-in-folder",
            "privacy": "public",
            "folder_id": folder_id,
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert deck_resp.status_code == 200

    # Retrieve folder contents
    get_resp = await async_client.get(
        f"/v1/folders/{folder_id}",
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert get_resp.status_code == 200
    data = get_resp.json()

    assert data["id"] == folder_id
    assert "folders" in data
    assert "decks" in data

    assert len(data["folders"]) == 1
    assert data["folders"][0]["id"] == child_folder_resp.json()["id"]

    assert len(data["decks"]) == 1
    assert data["decks"][0]["id"] == deck_resp.json()["id"]


@pytest.mark.asyncio
async def test_folder_privacy_filtering(
    async_client: AsyncClient, guest_token1: str, guest_token2: str
):
    # Create a public folder
    folder_resp = await async_client.post(
        "/v1/folders/",
        json={"name": "Mixed Folder", "slug": "mixed-folder", "privacy": "public"},
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert folder_resp.status_code == 200
    folder_id = folder_resp.json()["id"]

    # Create a public deck inside
    await async_client.post(
        "/v1/decks/",
        json={
            "name": "Public Deck",
            "slug": "public-deck",
            "privacy": "public",
            "folder_id": folder_id,
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )

    # Create an unlisted deck inside
    await async_client.post(
        "/v1/decks/",
        json={
            "name": "Unlisted Deck",
            "slug": "unlisted-deck",
            "privacy": "unlisted",
            "folder_id": folder_id,
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )

    # Create a private deck inside
    await async_client.post(
        "/v1/decks/",
        json={
            "name": "Private Deck",
            "slug": "private-deck",
            "privacy": "private",
            "folder_id": folder_id,
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )

    # Owner should see all decks
    owner_resp = await async_client.get(
        f"/v1/folders/{folder_id}",
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert owner_resp.status_code == 200
    owner_data = owner_resp.json()
    assert len(owner_data["decks"]) == 3

    # Another user (guest_token2) should only see public and unlisted decks
    other_resp = await async_client.get(
        f"/v1/folders/{folder_id}",
        headers={"Authorization": f"Bearer {guest_token2}"},
    )
    assert other_resp.status_code == 200
    other_data = other_resp.json()
    assert len(other_data["decks"]) == 2

    deck_names = [d["name"] for d in other_data["decks"]]
    assert "Public Deck" in deck_names
    assert "Unlisted Deck" in deck_names
    assert "Private Deck" not in deck_names


@pytest.mark.asyncio
async def test_create_folder_name_too_long(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/v1/folders/",
        json={"name": "A" * 81, "slug": "valid-slug", "privacy": "public"},
        headers={"Authorization": f"Bearer {guest_token1}"},
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
async def test_create_folder_invalid_slug(
    async_client: AsyncClient, guest_token1: str, invalid_slug: str
):
    response = await async_client.post(
        "/v1/folders/",
        json={"name": "Valid Name", "slug": invalid_slug, "privacy": "public"},
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_folder_invalid_privacy(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/v1/folders/",
        json={"name": "Valid Name", "slug": "valid-slug", "privacy": "super-secret"},
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_folder_non_existent_parent(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/v1/folders/",
        json={
            "name": "Valid Name",
            "slug": "valid-slug",
            "privacy": "public",
            "parent_id": 999999,
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code in (422, 404)


@pytest.mark.asyncio
async def test_create_folder_not_owned_parent(
    async_client: AsyncClient, guest_token1: str, guest_token2: str
):
    # Create folder with guest_token2
    parent_resp = await async_client.post(
        "/v1/folders/",
        json={
            "name": "Other User Folder",
            "slug": "other-user-folder",
            "privacy": "public",
        },
        headers={"Authorization": f"Bearer {guest_token2}"},
    )
    parent_id = parent_resp.json()["id"]

    # Try to create child folder with guest_token1
    response = await async_client.post(
        "/v1/folders/",
        json={
            "name": "Valid Name",
            "slug": "valid-slug",
            "privacy": "public",
            "parent_id": parent_id,
        },
        headers={"Authorization": f"Bearer {guest_token1}"},
    )
    assert response.status_code in (403, 404, 422)
