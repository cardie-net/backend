import logging

import boto3
from botocore.config import Config

from ..config import settings

logger = logging.getLogger(__name__)

# Object-key namespaces inside the S3 bucket
AVATAR_PREFIX = "avatars/"
CARD_IMAGE_PREFIX = "card-images/"


def get_s3_client():
    kwargs = {
        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
        "region_name": settings.AWS_REGION,
    }

    if settings.AWS_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL
        kwargs["config"] = Config(s3={"addressing_style": "path"})

    return boto3.client("s3", **kwargs)


def upload_file_to_s3(file_bytes: bytes, object_name: str, content_type: str) -> str:
    s3_client = get_s3_client()
    s3_client.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=object_name,
        Body=file_bytes,
        ContentType=content_type,
    )

    if settings.S3_PUBLIC_URL:
        endpoint = settings.S3_PUBLIC_URL.rstrip("/")
        return f"{endpoint}/{object_name}"
    elif settings.AWS_ENDPOINT_URL:
        endpoint = settings.AWS_ENDPOINT_URL.rstrip("/")
        return f"{endpoint}/{settings.S3_BUCKET_NAME}/{object_name}"
    else:
        return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{object_name}"


def delete_file_from_s3(object_name: str) -> None:
    s3_client = get_s3_client()
    try:
        s3_client.delete_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=object_name,
        )
    except Exception as e:
        logger.error(f"Failed to delete S3 object {object_name}: {e}")


def extract_object_name_from_url(url: str, prefix: str | None = None) -> str | None:
    if not url:
        return None
    if prefix is None:
        prefix = AVATAR_PREFIX
    if prefix in url:
        return url[url.find(prefix) :]
    return None


def delete_managed_images(urls: list[str], prefix: str | None = None) -> None:
    """Best-effort delete of S3 objects referenced by managed image URLs."""
    if prefix is None:
        prefix = CARD_IMAGE_PREFIX
    for url in urls:
        object_name = extract_object_name_from_url(url, prefix)
        if object_name:
            delete_file_from_s3(object_name)
