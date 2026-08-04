import pytest
from httpx import AsyncClient


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
async def test_create_deck_without_slug(async_client: AsyncClient, guest_token: str):
    response = await async_client.post(
        "/api/v1/decks",
        json={"name": "Test Deck Without Slug", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Deck Without Slug"
    assert "slug" in data
    assert len(data["slug"]) >= 1
    import re

    assert re.match(r"^[a-zA-Z0-9_-]+$", data["slug"])
    assert "id" in data


@pytest.mark.asyncio
async def test_create_deck_without_slug_unique(
    async_client: AsyncClient, guest_token: str
):
    response1 = await async_client.post(
        "/api/v1/decks",
        json={"name": "Duplicate Name", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )

    response2 = await async_client.post(
        "/api/v1/decks",
        json={"name": "Duplicate Name", "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["slug"] != response2.json()["slug"]


@pytest.mark.parametrize(
    "name, expected_min_len, expected_max_len",
    [
        ("A" * 80, 1, 80),  # Too long, should be cut off
        ("A", 1, 80),  # Too short, no padding
        ("Hello World! @#$ 😜", 1, 80),  # Unsafe chars, should be removed
        ("!@#$%^", 1, 80),  # Only unsafe chars, should fallback
    ],
)
@pytest.mark.asyncio
async def test_create_deck_without_slug_edge_cases(
    async_client: AsyncClient,
    guest_token: str,
    name: str,
    expected_min_len: int,
    expected_max_len: int,
):
    response = await async_client.post(
        "/api/v1/decks",
        json={"name": name, "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )

    assert response.status_code == 200
    data = response.json()
    slug = data["slug"]

    assert expected_min_len <= len(slug) <= expected_max_len
    import re

    # Must only contain lowercase alphanumeric characters and hyphens/underscores
    assert re.match(r"^[a-zA-Z0-9_-]+$", slug)


@pytest.mark.asyncio
async def test_create_deck_without_slug_uniqueness_max_length(
    async_client: AsyncClient, guest_token: str
):
    name = "B" * 80  # Max length name

    # First deck
    response1 = await async_client.post(
        "/api/v1/decks",
        json={"name": name, "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
    )
    assert response1.status_code == 200
    slug1 = response1.json()["slug"]
    assert len(slug1) <= 80

    # Second deck, same name
    response2 = await async_client.post(
        "/api/v1/decks",
        json={"name": name, "privacy": "private"},
        headers={"X-Test-Cookie": guest_token},
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
    assert response.status_code == 404


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
    assert response.status_code == 403


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
    assert delete_resp.status_code == 403


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
    assert patch_resp.status_code == 403


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
    assert data.get("properties")["color"] == "#ffffff"

    # Also test retrieve
    get_resp = await async_client.get(
        f"/api/v1/decks/{data['id']}",
        headers={"X-Test-Cookie": guest_token},
    )
    assert get_resp.status_code == 200
    assert get_resp.json().get("properties")["color"] == "#ffffff"


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


# --- Card image upload ---


@pytest.fixture
async def upload_deck_id(async_client: AsyncClient, guest_token: str) -> str:
    """Creates a private deck owned by guest_token for upload tests."""
    import uuid

    response = await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Upload Deck",
            "slug": f"upload-deck-{uuid.uuid4().hex[:8]}",
            "privacy": "private",
        },
        headers={"X-Test-Cookie": guest_token},
    )
    return response.json()["id"]


def _make_image_file() -> tuple[str, bytes, str]:
    import io

    from PIL import Image

    img = Image.new("RGB", (100, 100), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    return "test.jpg", img_byte_arr.getvalue(), "image/jpeg"


@pytest.mark.asyncio
async def test_upload_card_image_success(
    async_client: AsyncClient, guest_token: str, upload_deck_id: str
):
    from unittest.mock import patch

    files = {"file": _make_image_file()}

    with patch(
        "src.routers.decks.upload_file_to_s3",
        return_value="http://test-url/card-images/abc.webp",
    ):
        response = await async_client.post(
            f"/api/v1/decks/{upload_deck_id}/images",
            headers={"X-Test-Cookie": guest_token},
            files=files,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "http://test-url/card-images/abc.webp"


@pytest.mark.asyncio
async def test_upload_card_image_non_image(
    async_client: AsyncClient, guest_token: str, upload_deck_id: str
):
    files = {"file": ("a.txt", b"hello", "text/plain")}
    response = await async_client.post(
        f"/api/v1/decks/{upload_deck_id}/images",
        headers={"X-Test-Cookie": guest_token},
        files=files,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "File must be an image"


@pytest.mark.asyncio
async def test_upload_card_image_non_owner(
    async_client: AsyncClient, guest_token2: str, upload_deck_id: str
):
    files = {"file": _make_image_file()}
    response = await async_client.post(
        f"/api/v1/decks/{upload_deck_id}/images",
        headers={"X-Test-Cookie": guest_token2},
        files=files,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upload_card_image_deck_not_found(
    async_client: AsyncClient, guest_token: str
):
    files = {"file": _make_image_file()}
    response = await async_client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000999/images",
        headers={"X-Test-Cookie": guest_token},
        files=files,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_deck_cleans_up_card_images(
    async_client: AsyncClient, guest_token: str, upload_deck_id: str
):
    from unittest.mock import patch

    me_resp = await async_client.get(
        "/api/v1/users/me", headers={"X-Test-Cookie": guest_token}
    )
    user_id = me_resp.json()["id"]
    managed_url = f"https://cdn.example.com/card-images/{user_id}/deck/c.webp"
    card_resp = await async_client.post(
        f"/api/v1/decks/{upload_deck_id}/cards",
        json={
            "front": [{"type": "image", "url": managed_url}],
            "back": [{"type": "text", "content": "back"}],
        },
        headers={"X-Test-Cookie": guest_token},
    )
    assert card_resp.status_code == 200

    with patch("src.routers.decks.delete_managed_images") as mock_del:
        del_resp = await async_client.delete(
            f"/api/v1/decks/{upload_deck_id}",
            headers={"X-Test-Cookie": guest_token},
        )
    assert del_resp.status_code == 204
    mock_del.assert_called_once_with([managed_url], f"card-images/{user_id}/")


@pytest.mark.asyncio
async def test_upload_card_image_too_large(
    async_client: AsyncClient, guest_token: str, upload_deck_id: str
):
    from src.config import settings

    files = {"file": ("big.jpg", b"x" * (settings.MAX_UPLOAD_SIZE + 1), "image/jpeg")}
    response = await async_client.post(
        f"/api/v1/decks/{upload_deck_id}/images",
        headers={"X-Test-Cookie": guest_token},
        files=files,
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "File too large"


async def test_upload_deck_cover_success(
    async_client: AsyncClient, guest_token: str, upload_deck_id: str
):
    from unittest.mock import patch

    with patch(
        "src.routers.decks.upload_file_to_s3",
        return_value="https://s3.com/cover-images/user/deck/cover.webp",
    ) as mock_upload, patch(
        "src.routers.decks.delete_file_from_s3"
    ) as mock_delete, patch(
        "src.routers.decks.optimize_image", return_value=b"optimized"
    ):
        files = {"file": ("cover.jpg", b"fake_image_content", "image/jpeg")}
        response = await async_client.post(
            f"/api/v1/decks/{upload_deck_id}/cover",
            headers={"X-Test-Cookie": guest_token},
            files=files,
        )
        assert response.status_code == 200
        data = response.json()
        assert (
            data["properties"]["cover_image_url"]
            == "https://s3.com/cover-images/user/deck/cover.webp"
        )
        mock_upload.assert_called_once()
        mock_delete.assert_not_called()

        # Upload again to trigger delete
        files2 = {"file": ("cover2.jpg", b"fake_image_content2", "image/jpeg")}
        response2 = await async_client.post(
            f"/api/v1/decks/{upload_deck_id}/cover",
            headers={"X-Test-Cookie": guest_token},
            files=files2,
        )
        assert response2.status_code == 200
        mock_delete.assert_called_once()


async def test_delete_deck_cleans_up_cover_image(
    async_client: AsyncClient, guest_token: str, upload_deck_id: str
):
    from unittest.mock import patch

    await async_client.patch(
        f"/api/v1/decks/{upload_deck_id}",
        headers={"X-Test-Cookie": guest_token},
        json={
            "properties": {
                "cover_image_url": "https://s3.amazonaws.com/test-bucket/cover-images/test/test.webp"
            }
        },
    )

    with patch("src.routers.decks.delete_file_from_s3") as mock_del:
        resp = await async_client.delete(
            f"/api/v1/decks/{upload_deck_id}",
            headers={"X-Test-Cookie": guest_token},
        )
        assert resp.status_code == 204
        mock_del.assert_called_once()
        assert mock_del.call_args[0][0] == "cover-images/test/test.webp"


async def test_patch_deck_cleans_up_cover_image(
    async_client: AsyncClient, guest_token: str, upload_deck_id: str
):
    from unittest.mock import patch

    await async_client.patch(
        f"/api/v1/decks/{upload_deck_id}",
        headers={"X-Test-Cookie": guest_token},
        json={
            "properties": {
                "cover_image_url": "https://s3.amazonaws.com/test-bucket/cover-images/test/test.webp"
            }
        },
    )

    with patch("src.routers.decks.delete_file_from_s3") as mock_del:
        resp = await async_client.patch(
            f"/api/v1/decks/{upload_deck_id}",
            headers={"X-Test-Cookie": guest_token},
            json={"properties": {"cover_image_url": None}},
        )
        assert resp.status_code == 200
        mock_del.assert_called_once()
        assert mock_del.call_args[0][0] == "cover-images/test/test.webp"


async def test_patch_deck_description(
    async_client: AsyncClient, guest_token: str, upload_deck_id: str
):
    resp = await async_client.patch(
        f"/api/v1/decks/{upload_deck_id}",
        headers={"X-Test-Cookie": guest_token},
        json={"properties": {"description": "A very nice deck"}},
    )
    assert resp.status_code == 200
    assert resp.json()["properties"]["description"] == "A very nice deck"
