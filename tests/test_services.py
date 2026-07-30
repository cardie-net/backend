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
