import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..auth.utils import get_optional_current_user
from ..database import get_db

router = APIRouter(prefix="/community", tags=["community"])


@router.get("", response_model=models.CommunityResponse)
async def get_community(
    item_type: Literal["all", "deck", "folder"] = Query(default="all"),
    sort: Literal["popular", "created", "updated", "search"] = Query(default="popular"),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    threshold: float = Query(default=0.6, ge=0.0, le=1.0),
    user: models.User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> models.CommunityResponse:
    """Retrieve public community decks and folders with pagination and sorting."""
    user_id = user.id if user else None
    items, total = await crud.get_community_items(
        db=db,
        current_user_id=user_id,
        item_type=item_type,
        sort=sort,
        query=q,
        page=page,
        limit=limit,
        threshold=threshold,
    )
    total_pages = max(1, math.ceil(total / limit)) if total > 0 else 1
    has_more = page < total_pages

    return models.CommunityResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        has_more=has_more,
    )


@router.get("/starred", response_model=models.UserStarredResponse)
async def get_starred_items(
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> models.UserStarredResponse:
    """Retrieve all deck and folder IDs starred by the current user."""
    deck_ids, folder_ids = await crud.get_user_starred_ids(db=db, user_id=user.id)
    return models.UserStarredResponse(deck_ids=deck_ids, folder_ids=folder_ids)


@router.get("/favorites", response_model=list[models.CommunityItem])
async def get_favorite_items(
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[models.CommunityItem]:
    """Retrieve all favourited decks and folders for the current user."""
    return await crud.get_user_favorite_items(db=db, user_id=user.id)
