"""Per-user upload accounting: storage quota and upload rate limiting."""

import time
import uuid
from collections import deque

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import UploadedImage

RATE_LIMIT_WINDOW_SECONDS = 60
# Bounds the in-process rate-limit map; stale entries are pruned past this size.
_MAX_TRACKED_USERS = 10_000


class _UploadRateLimiter:
    """In-process sliding-window limiter keyed by user id.

    State is per worker process, so it is a backstop against abusive clients
    rather than an exact cluster-wide quota.
    """

    def __init__(self) -> None:
        self._windows: dict[uuid.UUID, deque[float]] = {}

    def check(self, user_id: uuid.UUID) -> None:
        """Raise 429 when the user exceeded UPLOAD_RATE_LIMIT_PER_MINUTE."""
        limit = settings.UPLOAD_RATE_LIMIT_PER_MINUTE
        if limit <= 0:
            return

        now = time.monotonic()
        window = self._windows.setdefault(user_id, deque())
        while window and now - window[0] >= RATE_LIMIT_WINDOW_SECONDS:
            window.popleft()

        if len(window) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many uploads, try again later",
                headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
            )

        window.append(now)
        if len(self._windows) > _MAX_TRACKED_USERS:
            self._prune(now)

    def reset(self) -> None:
        self._windows.clear()

    def _prune(self, now: float) -> None:
        stale = [
            user_id
            for user_id, window in self._windows.items()
            if not window or now - window[-1] >= RATE_LIMIT_WINDOW_SECONDS
        ]
        for user_id in stale:
            self._windows.pop(user_id, None)


upload_rate_limiter = _UploadRateLimiter()


def enforce_upload_rate_limit(user_id: uuid.UUID) -> None:
    """Raise 429 when the user has uploaded too many images this minute."""
    upload_rate_limiter.check(user_id)


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
