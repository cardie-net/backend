import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.config import settings
from src.services.image_service import optimize_image
from src.services.s3_service import upload_file_to_s3


def test_optimize_image():
    # Create a simple test image
    img = Image.new("RGB", (1000, 1000), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    optimized = optimize_image(img_bytes, max_size=(512, 512))

    # Verify the output
    assert isinstance(optimized, bytes)
    with Image.open(io.BytesIO(optimized)) as result_img:
        assert result_img.format == "WEBP"
        assert result_img.size[0] <= 512
        assert result_img.size[1] <= 512


@patch("src.services.s3_service.get_s3_client")
def test_upload_file_to_s3(mock_get_s3_client, monkeypatch):
    mock_client = MagicMock()
    mock_get_s3_client.return_value = mock_client

    test_bytes = b"testdata"
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(settings, "AWS_ENDPOINT_URL", "http://test-endpoint")
    monkeypatch.setattr(settings, "S3_PUBLIC_URL", None)

    result = upload_file_to_s3(test_bytes, "test_key", "image/webp")

    mock_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="test_key",
        Body=test_bytes,
        ContentType="image/webp",
    )

    assert result == "http://test-endpoint/test-bucket/test_key"


@patch("src.services.s3_service.get_s3_client")
def test_delete_file_from_s3(mock_get_s3_client, monkeypatch):
    from src.services.s3_service import delete_file_from_s3

    mock_client = MagicMock()
    mock_get_s3_client.return_value = mock_client

    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "test-bucket")

    delete_file_from_s3("test_key")

    mock_client.delete_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="test_key",
    )


@patch("src.services.email.smtplib")
@pytest.mark.asyncio
async def test_send_email_success(mock_smtplib, monkeypatch):
    from src.services.email import _background_tasks, send_email

    monkeypatch.setattr(settings, "SMTP_SERVER", "smtp.test.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "test@test.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")

    mock_server_instance = MagicMock()
    mock_smtplib.SMTP.return_value.__enter__.return_value = mock_server_instance

    await send_email("recipient@test.com", "Test Subject", "Test Body")

    if _background_tasks:
        await asyncio.gather(*_background_tasks)

    mock_server_instance.send_message.assert_called_once()


@patch("src.services.s3_service.delete_file_from_s3")
def test_delete_managed_images_filters_external(mock_delete):
    from src.services.s3_service import delete_managed_images

    delete_managed_images(
        [
            "https://cdn.example.com/card-images/u/d/c.webp",
            "https://imgur.com/x.png",
            "",
        ]
    )

    mock_delete.assert_called_once_with("card-images/u/d/c.webp")


def test_extract_object_name_from_url_prefix():
    from src.services.s3_service import extract_object_name_from_url

    # Card prefix: only card-image URLs extract an object name
    card_url = "https://cdn.example.com/card-images/u/d/c.webp"
    assert (
        extract_object_name_from_url(card_url, "card-images/")
        == "card-images/u/d/c.webp"
    )
    assert extract_object_name_from_url(card_url, "avatars/") is None

    # Avatar default stays backward compatible
    avatar_url = "https://cdn.example.com/avatars/u/a.webp"
    assert extract_object_name_from_url(avatar_url) == "avatars/u/a.webp"
    assert extract_object_name_from_url("https://imgur.com/x.png") is None
    assert extract_object_name_from_url(None) is None
    assert extract_object_name_from_url("") is None


def test_collect_image_urls_mixed():
    from src.services.image_service import collect_image_urls

    elements = [
        {"type": "text", "content": "hi"},
        {"type": "image", "url": "https://cdn.example.com/card-images/a.webp"},
    ]
    assert collect_image_urls(elements) == [
        "https://cdn.example.com/card-images/a.webp"
    ]
    assert collect_image_urls([]) == []
    assert collect_image_urls(None) == []
    assert collect_image_urls(elements, [{"type": "image", "url": "b.webp"}]) == [
        "https://cdn.example.com/card-images/a.webp",
        "b.webp",
    ]


@patch("src.services.s3_service.delete_file_from_s3")
def test_delete_managed_images_user_scoped(mock_delete):
    """Only objects under the caller's card-image namespace are deleted."""
    from src.services.s3_service import delete_managed_images

    own_prefix = "card-images/user-a/"

    delete_managed_images(
        [
            "https://cdn.example.com/card-images/user-a/deck/c.webp",
            "https://cdn.example.com/card-images/user-b/deck/c.webp",
        ],
        prefix=own_prefix,
    )

    mock_delete.assert_called_once_with("card-images/user-a/deck/c.webp")


def test_extract_object_name_from_url_user_scoped():
    from src.services.s3_service import extract_object_name_from_url

    own = extract_object_name_from_url(
        "https://cdn.example.com/card-images/user-a/deck/c.webp",
        "card-images/user-a/",
    )
    assert own == "card-images/user-a/deck/c.webp"

    # Another user's object under the same prefix family must not match
    other = extract_object_name_from_url(
        "https://cdn.example.com/card-images/user-b/deck/c.webp",
        "card-images/user-a/",
    )
    assert other is None
