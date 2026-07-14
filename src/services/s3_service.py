import boto3
from botocore.config import Config

from src.config import settings


def get_s3_client():
    kwargs = {
        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
        "region_name": settings.AWS_REGION,
    }

    print(settings.AWS_ACCESS_KEY_ID)

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
        return f"https://{settings.S3_BUCKET_NAME}/{object_name}"
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
        print(f"Failed to delete S3 object {object_name}: {e}")


def extract_object_name_from_url(url: str) -> str | None:
    if not url:
        return None
    if "avatars/" in url:
        return url[url.find("avatars/") :]
    return None
