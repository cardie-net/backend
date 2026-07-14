import boto3
from botocore.config import Config

from src.config import settings


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

    if settings.AWS_ENDPOINT_URL:
        endpoint = settings.AWS_ENDPOINT_URL.rstrip("/")
        return f"{endpoint}/{settings.S3_BUCKET_NAME}/{object_name}"
    else:
        return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{object_name}"
