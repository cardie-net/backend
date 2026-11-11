"""Per-user upload accounting: storage quota and upload rate limiting."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import UploadedImage
from .rate_limit import SlidingWindowLimiter

RATE_LIMIT_WINDOW_SECONDS = 60

upload_rate_limiter = SlidingWindowLimiter(
    detail="Too many uploads, try again later",
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)


def enforce_upload_rate_limit(user_id: uuid.UUID) -> None:
    """Raise 429 when the user has uploaded too many images this minute."""
    upload_rate_limiter.check(user_id, settings.UPLOAD_RATE_LIMIT_PER_MINUTE)


async def get_used_bytes(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Total image bytes currently accounted to a user."""
    result = await db.execute(
        select(func.coalesce(func.sum(UploadedImage.size_bytes), 0)).where(
            UploadedImage.user_id == user_id
        )
    )
    return int(result.scalar() or 0)


async def enforce_storage_quota(
    db: AsyncSession, user_id: uuid.UUID, new_bytes: int
) -> None:
    """Raise 413 when storing new_bytes would exceed MAX_USER_STORAGE_BYTES."""
    limit = settings.MAX_USER_STORAGE_BYTES
    if limit <= 0:
        return

    used = await get_used_bytes(db, user_id)
    if used + new_bytes > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Storage quota exceeded",
        )


async def record_upload(
    db: AsyncSession, user_id: uuid.UUID, key: str, size_bytes: int
) -> None:
    """Account for a stored image; committed with the caller's transaction."""
    db.add(UploadedImage(user_id=user_id, key=key, size_bytes=size_bytes))
    await db.commit()


async def release_uploads(
    db: AsyncSession, user_id: uuid.UUID, keys: list[str]
) -> None:
    """Forget stored images that were deleted, freeing their quota."""
    keys = [key for key in keys if key]
    if not keys:
        return
    await db.execute(
        delete(UploadedImage).where(
            UploadedImage.user_id == user_id, UploadedImage.key.in_(keys)
        )
    )
    await db.commit()
