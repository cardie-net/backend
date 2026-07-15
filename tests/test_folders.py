import pytest
from httpx import AsyncClient


@pytest.fixture
async def guest_token1(async_client: AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/guest")
    return response.cookies.get("cardie_session")


@pytest.fixture
async def guest_token2(async_client: AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/guest")
    return response.cookies.get("cardie_session")


@pytest.mark.asyncio
async def test_create_folder(async_client: AsyncClient, guest_token1: str):
    response = await async_client.post(
        "/api/v1/folders",
        json={"name": "Test Folder", "slug": "test-folder", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Folder"
    assert data["slug"] == "test-folder"
    assert data["privacy"] == "public"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_folder_without_slug(async_client: AsyncClient, guest_token1: str):
    response = await async_client.post(
        "/api/v1/folders",
        json={"name": "Test Folder Without Slug", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Folder Without Slug"
    assert "slug" in data
    assert len(data["slug"]) >= 8
    import re

    assert re.match(r"^[a-zA-Z0-9_-]+$", data["slug"])
    assert "id" in data


@pytest.mark.asyncio
async def test_create_folder_without_slug_unique(
    async_client: AsyncClient, guest_token1: str
):
    response1 = await async_client.post(
        "/api/v1/folders",
        json={"name": "Duplicate Name", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )

    response2 = await async_client.post(
        "/api/v1/folders",
        json={"name": "Duplicate Name", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["slug"] != response2.json()["slug"]


@pytest.mark.parametrize(
    "name, expected_min_len, expected_max_len",
    [
        ("A" * 80, 8, 80),  # Too long, should be cut off
        ("A", 8, 80),  # Too short, should be padded
        ("Hello World! @#$ 😜", 8, 80),  # Unsafe chars, should be removed
        ("!@#$%^", 8, 80),  # Only unsafe chars, should fallback and pad
    ],
)
@pytest.mark.asyncio
async def test_create_folder_without_slug_edge_cases(
    async_client: AsyncClient,
    guest_token1: str,
    name: str,
    expected_min_len: int,
    expected_max_len: int,
):
    response = await async_client.post(
        "/api/v1/folders",
        json={"name": name, "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )

    assert response.status_code == 200
    data = response.json()
    slug = data["slug"]

    assert expected_min_len <= len(slug) <= expected_max_len
    import re

    # Must only contain lowercase alphanumeric characters and hyphens/underscores
    assert re.match(r"^[a-zA-Z0-9_-]+$", slug)


@pytest.mark.asyncio
async def test_create_folder_without_slug_uniqueness_max_length(
    async_client: AsyncClient, guest_token1: str
):
    name = "B" * 80  # Max length name

    # First folder
    response1 = await async_client.post(
        "/api/v1/folders",
        json={"name": name, "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response1.status_code == 200
    slug1 = response1.json()["slug"]
    assert len(slug1) <= 80

    # Second folder, same name
    response2 = await async_client.post(
        "/api/v1/folders",
        json={"name": name, "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response2.status_code == 200
    slug2 = response2.json()["slug"]

    assert slug1 != slug2
    assert len(slug2) <= 80

    # Verify both slugs have the valid pattern
    import re

    assert re.match(r"^[a-zA-Z0-9_-]+$", slug1)
    assert re.match(r"^[a-zA-Z0-9_-]+$", slug2)


@pytest.mark.asyncio
async def test_create_folder_name_too_long(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/api/v1/folders",
        json={"name": "A" * 81, "slug": "valid-slug", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
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
        "/api/v1/folders",
        json={"name": "Valid Name", "slug": invalid_slug, "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_folder_invalid_privacy(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/api/v1/folders",
        json={"name": "Valid Name", "slug": "valid-slug", "privacy": "super-secret"},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_folder_non_existent_parent(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/api/v1/folders",
        json={
            "name": "Valid Name",
            "slug": "valid-slug",
            "privacy": "public",
            "parent_id": "00000000-0000-0000-0000-000000999999",
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code in (422, 404)


@pytest.mark.asyncio
async def test_create_folder_not_owned_parent(
    async_client: AsyncClient, guest_token1: str, guest_token2: str
):
    # Create folder with guest_token2
    parent_resp = await async_client.post(
        "/api/v1/folders",
        json={
            "name": "Other User Folder",
            "slug": "other-user-folder",
            "privacy": "public",
        },
        headers={"X-Test-Cookie": guest_token2},
    )
    parent_id = parent_resp.json()["id"]

    # Try to create child folder with guest_token1
    response = await async_client.post(
        "/api/v1/folders",
        json={
            "name": "Valid Name",
            "slug": "valid-slug",
            "privacy": "public",
            "parent_id": parent_id,
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code in (403, 404, 422)


@pytest.mark.asyncio
async def test_delete_folder_success(async_client: AsyncClient, guest_token1: str):
    # Create folder
    create_resp = await async_client.post(
        "/api/v1/folders",
        json={"name": "To Delete", "slug": "to-delete", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    folder_id = create_resp.json()["id"]

    # Delete folder
    delete_resp = await async_client.delete(
        f"/api/v1/folders/{folder_id}",
        headers={"X-Test-Cookie": guest_token1},
    )
    assert delete_resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_folder_not_owned(
    async_client: AsyncClient, guest_token1: str, guest_token2: str
):
    # Create folder with guest_token1
    create_resp = await async_client.post(
        "/api/v1/folders",
        json={"name": "Not Yours", "slug": "not-yours", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    folder_id = create_resp.json()["id"]

    # Try to delete with guest_token2
    delete_resp = await async_client.delete(
        f"/api/v1/folders/{folder_id}",
        headers={"X-Test-Cookie": guest_token2},
    )
    assert delete_resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_delete_folder_not_found(async_client: AsyncClient, guest_token1: str):
    delete_resp = await async_client.delete(
        "/api/v1/folders/00000000-0000-0000-0000-000000999999",
        headers={"X-Test-Cookie": guest_token1},
    )
    assert delete_resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_folder_success(async_client: AsyncClient, guest_token1: str):
    # Create folder
    create_resp = await async_client.post(
        "/api/v1/folders",
        json={"name": "Old Name", "slug": "old-slug", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    folder_id = create_resp.json()["id"]

    # Patch folder
    patch_resp = await async_client.patch(
        f"/api/v1/folders/{folder_id}",
        json={"name": "New Name", "slug": "new-slug", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["name"] == "New Name"
    assert data["slug"] == "new-slug"
    assert data["privacy"] == "private"


@pytest.mark.asyncio
async def test_patch_folder_parent_id(async_client: AsyncClient, guest_token1: str):
    # Create parent folder
    parent_resp = await async_client.post(
        "/api/v1/folders",
        json={"name": "Parent", "slug": "parent", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    parent_id = parent_resp.json()["id"]

    # Create child folder
    child_resp = await async_client.post(
        "/api/v1/folders",
        json={"name": "Child", "slug": "child", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    child_id = child_resp.json()["id"]

    # Patch child's parent_id
    patch_resp = await async_client.patch(
        f"/api/v1/folders/{child_id}",
        json={"parent_id": parent_id},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["parent_id"] == parent_id


@pytest.mark.asyncio
async def test_patch_folder_not_owned(
    async_client: AsyncClient, guest_token1: str, guest_token2: str
):
    # Create folder with guest_token1
    create_resp = await async_client.post(
        "/api/v1/folders",
        json={"name": "Not Yours", "slug": "not-yours", "privacy": "public"},
        headers={"X-Test-Cookie": guest_token1},
    )
    folder_id = create_resp.json()["id"]

    # Try to patch with guest_token2
    patch_resp = await async_client.patch(
        f"/api/v1/folders/{folder_id}",
        json={"name": "Hacked Name"},
        headers={"X-Test-Cookie": guest_token2},
    )
    assert patch_resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_patch_folder_not_found(async_client: AsyncClient, guest_token1: str):
    patch_resp = await async_client.patch(
        "/api/v1/folders/00000000-0000-0000-0000-000000999999",
        json={"name": "New Name"},
        headers={"X-Test-Cookie": guest_token1},
    )
    assert patch_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_folder_cascades_decks_and_cards(
    async_client: AsyncClient, guest_token1: str, async_session
):
    import uuid

    from src import models

    unique_slug = f"folder-cascades-{uuid.uuid4().hex[:8]}"

    # Create folder
    folder_resp = await async_client.post(
        "/api/v1/folders",
        json={"name": "Folder for Cascades", "slug": unique_slug, "privacy": "private"},
        headers={"X-Test-Cookie": guest_token1},
    )
    folder_id = folder_resp.json()["id"]

    # Create deck in folder
    deck_resp = await async_client.post(
        "/api/v1/decks/",
        json={
            "name": "Deck in Folder",
            "slug": f"deck-{unique_slug}",
            "privacy": "private",
            "folder_id": folder_id,
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    deck_id = deck_resp.json()["id"]

    # Create card in deck
    card_resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/cards/",
        json={
            "front": [{"type": "text", "content": "front"}],
            "back": [{"type": "text", "content": "back"}],
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    card_id = card_resp.json()["id"]

    # Delete folder
    delete_resp = await async_client.delete(
        f"/api/v1/folders/{folder_id}",
        headers={"X-Test-Cookie": guest_token1},
    )
    assert delete_resp.status_code == 200

    # Verify deck is deleted
    deck = await async_session.get(models.Deck, uuid.UUID(deck_id))
    assert deck is None

    # Verify card is deleted
    card = await async_session.get(models.Card, uuid.UUID(card_id))
    assert card is None


@pytest.mark.asyncio
async def test_create_folder_with_properties(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/api/v1/folders",
        json={
            "name": "Folder Properties",
            "slug": "folder-properties",
            "privacy": "public",
            "properties": {"color": "#ff0000"},
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("properties") == {"color": "#ff0000"}


@pytest.mark.asyncio
async def test_create_folder_empty_properties(
    async_client: AsyncClient, guest_token1: str
):
    response = await async_client.post(
        "/api/v1/folders",
        json={
            "name": "Folder Empty Prop",
            "slug": "folder-empty-prop",
            "privacy": "public",
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response.status_code == 200
    assert "properties" not in response.json() or response.json()["properties"] in (
        None,
        {},
    )


@pytest.mark.asyncio
async def test_create_folder_invalid_properties(
    async_client: AsyncClient, guest_token1: str
):
    # invalid color type
    response1 = await async_client.post(
        "/api/v1/folders",
        json={
            "name": "Folder Inv Prop",
            "slug": "folder-inv-prop1",
            "privacy": "public",
            "properties": {"color": 123},
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response1.status_code == 422

    # invalid property key
    response2 = await async_client.post(
        "/api/v1/folders",
        json={
            "name": "Folder Inv Prop 2",
            "slug": "folder-inv-prop2",
            "privacy": "public",
            "properties": {"invalid_prop": "test"},
        },
        headers={"X-Test-Cookie": guest_token1},
    )
    assert response2.status_code == 422
