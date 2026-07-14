import asyncio
import uuid
from typing import List, Union

import fastapi
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..auth.user_manager import UserManager, get_user_manager
from ..database import get_db
from ..services.image_service import optimize_image
from ..services.s3_service import upload_file_to_s3

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


@router.post("/me/avatar", response_model=models.UserRead)
async def upload_avatar(
    file: fastapi.UploadFile = fastapi.File(...),
    user: models.User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    if not file.content_type.startswith("image/"):
        raise fastapi.HTTPException(status_code=400, detail="File must be an image")

    try:
        contents = await file.read()

        # Optimize image in a separate thread
        optimized_bytes = await asyncio.to_thread(optimize_image, contents)

        # Upload to S3
        file_extension = "webp"
        object_name = f"avatars/{user.id}/{uuid.uuid4()}.{file_extension}"
        avatar_url = await asyncio.to_thread(
            upload_file_to_s3, optimized_bytes, object_name, "image/webp"
        )

        # Update user
        user_update = models.UserUpdate(avatar_url=avatar_url)
        user = await user_manager.update(user_update, user, safe=True)

        return user
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))


@router.get("/profile/{username}", response_model=models.UserRead)
async def get_user_profile(
    username: str,
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    from sqlalchemy.future import select

    result = await db.execute(
        select(models.User).where(models.User.username == username)
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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
