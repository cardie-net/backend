import uuid
from typing import List, Union

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..database import get_db

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=models.UserRead)
async def get_current_user(user: models.User = Depends(current_active_user)):
    return user


@router.get(
    "/{user_id}/items", response_model=List[Union[models.FolderRead, models.DeckRead]]
)
async def get_user_items(
    user_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    items = await crud.get_user_items(
        db, target_user_id=user_id, requesting_user_id=user.id
    )
    return items
