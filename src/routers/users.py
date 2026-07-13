import uuid
from typing import List, Union

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..auth.user_manager import UserManager, get_user_manager
from ..database import get_db

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=models.UserRead)
async def get_current_user(user: models.User = Depends(current_active_user)):
    return user


@router.patch("/me", response_model=models.UserRead)
async def update_current_user(
    user_update: models.UserUpdate,
    user: models.User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    try:
        user = await user_manager.update(user_update, user, safe=True)
        return user
    except Exception as e:
        import sqlalchemy.exc
        from fastapi import HTTPException, status

        if isinstance(e, sqlalchemy.exc.IntegrityError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="USERNAME_ALREADY_EXISTS",
            )
        raise e


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
