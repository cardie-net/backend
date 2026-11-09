"""Security regression tests for user content uploads."""

import io
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlmodel import select

from src.config import settings
from src.models import User
from src.services.upload_limits import get_used_bytes, upload_rate_limiter


def _jpeg_with_metadata(size: tuple[int, int] = (100, 100)) -> bytes:
    """Build a JPEG carrying EXIF, GPS, comment and ICC metadata."""
    img = Image.new("RGB", size, color="red")
    exif = Image.Exif()
    exif[0x010E] = "injected description"
    exif[0x013B] = "attacker"
    exif[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0)}
    buf = io.BytesIO()
    img.save(
        buf,
        format="JPEG",
        exif=exif.tobytes(),
        comment=b"comment payload",
        icc_profile=b"\x00" * 64,
    )
    return buf.getvalue()


def _png(size: tuple[int, int] = (10, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color="red").save(buf, format="PNG")
    return buf.getvalue()


async def _user_id(async_client: AsyncClient, token: str) -> str:
    resp = await async_client.get("/api/v1/users/me", headers={"X-Test-Cookie": token})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_guest_cannot_upload_images(async_client: AsyncClient, guest_token1: str):
    """Anonymous accounts must not be able to store images."""
    deck = await async_client.post(
        "/api/v1/decks",
        json={"name": "guest deck"},
        headers={"X-Test-Cookie": guest_token1},
    )
    deck_id = deck.json()["id"]
    folder = await async_client.post(
        "/api/v1/folders",
        json={"name": "guest folder"},
        headers={"X-Test-Cookie": guest_token1},
    )
    folder_id = folder.json()["id"]

    payload = _png()
    for url in (
        f"/api/v1/decks/{deck_id}/images",
        f"/api/v1/decks/{deck_id}/cover",
        f"/api/v1/folders/{folder_id}/cover",
    ):
        resp = await async_client.post(
            url,
            files={"file": ("a.png", payload, "image/png")},
            headers={"X-Test-Cookie": guest_token1},
        )
        assert resp.status_code == 403, url
        assert resp.json()["detail"] == "Guest users cannot upload images"


@pytest.mark.asyncio
async def test_patch_me_cannot_set_avatar_url(
    async_client: AsyncClient, user_token: str
):
    """avatar_url is server-managed: it must never be writable via PATCH."""
    resp = await async_client.patch(
        "/api/v1/users/me",
        json={"avatar_url": "https://cdn.example.com/avatars/other/x.webp"},
        headers={"X-Test-Cookie": user_token},
    )
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None


@pytest.mark.asyncio
async def test_remove_avatar_never_deletes_foreign_object(
    async_client: AsyncClient, user_token: str, async_session
):
    """A stale/foreign avatar_url must not be turned into an S3 delete."""
    me = await async_client.get(
        "/api/v1/users/me", headers={"X-Test-Cookie": user_token}
    )
    user_id = me.json()["id"]

    result = await async_session.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalars().first()
    user.avatar_url = (
        f"https://cdn.example.com/avatars/{uuid.uuid4()}/{uuid.uuid4()}.webp"
    )
    async_session.add(user)
    await async_session.commit()

    with patch("src.routers.users.delete_file_from_s3") as mock_delete:
        resp = await async_client.delete(
            "/api/v1/users/me/avatar", headers={"X-Test-Cookie": user_token}
        )

    assert resp.status_code == 200
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_upload_avatar_uses_unique_owned_key_and_strips_metadata(
    async_client: AsyncClient, user_token: str
):
    user_id = await _user_id(async_client, user_token)
    uploads: list[bytes] = []

    def _capture(file_bytes: bytes, object_name: str, content_type: str) -> str:
        uploads.append(file_bytes)
        return f"https://cdn.example.com/{object_name}"

    with patch("src.routers.users.upload_file_to_s3", side_effect=_capture) as mock_up:
        for _ in range(2):
            resp = await async_client.post(
                "/api/v1/users/me/avatar",
                files={"file": ("a.jpg", _jpeg_with_metadata(), "image/jpeg")},
                headers={"X-Test-Cookie": user_token},
            )
            assert resp.status_code == 200

    keys = [call.args[1] for call in mock_up.call_args_list]
    assert all(key.startswith(f"avatars/{user_id}/") for key in keys)
    assert keys[0] != keys[1], "each upload must get a fresh key"
    assert all(key.endswith(".webp") for key in keys)
    assert all(call.args[2] == "image/webp" for call in mock_up.call_args_list)

    with Image.open(io.BytesIO(uploads[0])) as stored:
        assert stored.format == "WEBP"
        assert dict(stored.getexif()) == {}
        assert "comment" not in stored.info
        assert "icc_profile" not in stored.info


@pytest.mark.asyncio
async def test_upload_with_spoofed_image_content_type_is_rejected(
    async_client: AsyncClient, user_token: str
):
    deck = await async_client.post(
        "/api/v1/decks",
        json={"name": "spoof"},
        headers={"X-Test-Cookie": user_token},
    )
    deck_id = deck.json()["id"]

    payload = b"<?php echo 'not an image'; ?>"
    resp = await async_client.post(
        "/api/v1/users/me/avatar",
        files={"file": ("payload.png", payload, "image/png")},
        headers={"X-Test-Cookie": user_token},
    )
    assert resp.status_code == 415

    resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/images",
        files={"file": ("payload.png", payload, "image/png")},
        headers={"X-Test-Cookie": user_token},
    )
    assert resp.status_code == 415

    resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/cover",
        files={"file": ("payload.png", payload, "image/png")},
        headers={"X-Test-Cookie": user_token},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_pixel_limit_is_enforced(
    async_client: AsyncClient, user_token: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "MAX_IMAGE_PIXELS", 100)
    deck = await async_client.post(
        "/api/v1/decks",
        json={"name": "too many pixels"},
        headers={"X-Test-Cookie": user_token},
    )
    deck_id = deck.json()["id"]

    resp = await async_client.post(
        f"/api/v1/decks/{deck_id}/images",
        files={"file": ("big.png", _png((40, 40)), "image/png")},
        headers={"X-Test-Cookie": user_token},
    )
    assert resp.status_code == 413
    body = resp.json()
    assert body["detail"] == "Image dimensions too large"
    assert body["max_pixels"] == 100


@pytest.mark.asyncio
async def test_deck_cover_must_live_in_own_namespace(
    async_client: AsyncClient, user_token: str
):
    user_id = await _user_id(async_client, user_token)
    foreign_url = (
        f"https://cdn.example.com/cover-images/{uuid.uuid4()}/{uuid.uuid4()}/c.webp"
    )

    create = await async_client.post(
        "/api/v1/decks",
        json={"name": "cover", "properties": {"cover_image_url": foreign_url}},
        headers={"X-Test-Cookie": user_token},
    )
    assert create.status_code == 400

    deck = await async_client.post(
        "/api/v1/decks",
        json={"name": "cover"},
        headers={"X-Test-Cookie": user_token},
    )
    deck_id = deck.json()["id"]

    patch_foreign = await async_client.patch(
        f"/api/v1/decks/{deck_id}",
        json={"properties": {"cover_image_url": foreign_url}},
        headers={"X-Test-Cookie": user_token},
    )
    assert patch_foreign.status_code == 400

    own_url = f"https://cdn.example.com/cover-images/{user_id}/{deck_id}/c.webp"
    patch_own = await async_client.patch(
        f"/api/v1/decks/{deck_id}",
        json={"properties": {"cover_image_url": own_url}},
        headers={"X-Test-Cookie": user_token},
    )
    assert patch_own.status_code == 200
    assert patch_own.json()["properties"]["cover_image_url"] == own_url

    cleared = await async_client.patch(
        f"/api/v1/decks/{deck_id}",
        json={"properties": {"cover_image_url": None}},
        headers={"X-Test-Cookie": user_token},
    )
    assert cleared.status_code == 200
    assert cleared.json()["properties"]["cover_image_url"] is None


@pytest.mark.asyncio
async def test_folder_cover_must_live_in_own_namespace(
    async_client: AsyncClient, user_token: str
):
    foreign_url = (
        f"https://cdn.example.com/cover-images/{uuid.uuid4()}/{uuid.uuid4()}/c.webp"
    )

    create = await async_client.post(
        "/api/v1/folders",
        json={"name": "cover", "properties": {"cover_image_url": foreign_url}},
        headers={"X-Test-Cookie": user_token},
    )
    assert create.status_code == 400

    folder = await async_client.post(
        "/api/v1/folders",
        json={"name": "cover"},
        headers={"X-Test-Cookie": user_token},
    )
    folder_id = folder.json()["id"]

    patch_foreign = await async_client.patch(
        f"/api/v1/folders/{folder_id}",
        json={"properties": {"cover_image_url": foreign_url}},
        headers={"X-Test-Cookie": user_token},
    )
    assert patch_foreign.status_code == 400


@pytest.mark.asyncio
async def test_deck_import_cover_must_live_in_own_namespace(
    async_client: AsyncClient, user_token: str
):
    foreign_url = (
        f"https://cdn.example.com/cover-images/{uuid.uuid4()}/{uuid.uuid4()}/c.webp"
    )
    resp = await async_client.post(
        "/api/v1/decks/import",
        json={
            "name": "imported",
            "properties": {"cover_image_url": foreign_url},
            "cards": [{"front": [{"type": "text", "content": "a"}], "back": []}],
        },
        headers={"X-Test-Cookie": user_token},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_storage_quota_rejects_upload_over_limit(
    async_client: AsyncClient,
    user_token: str,
    async_session,
    monkeypatch: pytest.MonkeyPatch,
):
    """Once a user's accounted bytes reach the quota, further uploads are 413."""
    user_id = uuid.UUID(await _user_id(async_client, user_token))

    with patch(
        "src.routers.users.upload_file_to_s3",
        side_effect=lambda data, key, ctype: f"https://cdn.example.com/{key}",
    ):
        first = await async_client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("a.png", _png((32, 32)), "image/png")},
            headers={"X-Test-Cookie": user_token},
        )
    assert first.status_code == 200

    used = await get_used_bytes(async_session, user_id)
    assert used > 0

    monkeypatch.setattr(settings, "MAX_USER_STORAGE_BYTES", used)

    with patch(
        "src.routers.users.upload_file_to_s3",
        side_effect=lambda data, key, ctype: f"https://cdn.example.com/{key}",
    ) as upload_mock:
        second = await async_client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("b.png", _png((32, 32)), "image/png")},
            headers={"X-Test-Cookie": user_token},
        )

    assert second.status_code == 413
    assert second.json()["detail"] == "Storage quota exceeded"
    upload_mock.assert_not_called()


@pytest.mark.asyncio
async def test_deleting_avatar_releases_quota(
    async_client: AsyncClient, user_token: str, async_session
):
    user_id = uuid.UUID(await _user_id(async_client, user_token))

    with patch(
        "src.routers.users.upload_file_to_s3",
        side_effect=lambda data, key, ctype: f"https://cdn.example.com/{key}",
    ):
        with patch("src.routers.users.delete_file_from_s3"):
            resp = await async_client.post(
                "/api/v1/users/me/avatar",
                files={"file": ("a.png", _png((32, 32)), "image/png")},
                headers={"X-Test-Cookie": user_token},
            )
            assert resp.status_code == 200
            assert await get_used_bytes(async_session, user_id) > 0

            removed = await async_client.delete(
                "/api/v1/users/me/avatar", headers={"X-Test-Cookie": user_token}
            )

    assert removed.status_code == 200
    assert await get_used_bytes(async_session, user_id) == 0


@pytest.mark.asyncio
async def test_upload_rate_limit(
    async_client: AsyncClient, user_token: str, monkeypatch: pytest.MonkeyPatch
):
    upload_rate_limiter.reset()
    monkeypatch.setattr(settings, "UPLOAD_RATE_LIMIT_PER_MINUTE", 1)

    try:
        with patch(
            "src.routers.users.upload_file_to_s3",
            side_effect=lambda data, key, ctype: f"https://cdn.example.com/{key}",
        ):
            first = await async_client.post(
                "/api/v1/users/me/avatar",
                files={"file": ("a.png", _png((16, 16)), "image/png")},
                headers={"X-Test-Cookie": user_token},
            )
            assert first.status_code == 200

            second = await async_client.post(
                "/api/v1/users/me/avatar",
                files={"file": ("b.png", _png((16, 16)), "image/png")},
                headers={"X-Test-Cookie": user_token},
            )
    finally:
        upload_rate_limiter.reset()

    assert second.status_code == 429
    assert second.json()["detail"] == "Too many uploads, try again later"
    assert second.headers["retry-after"] == "60"
