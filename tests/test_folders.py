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
            "parent_id": "00000000-0000-0000-0000-000000999999",
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
