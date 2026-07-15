import asyncio
import uuid
from typing import Dict, List, Optional, Union

import fastapi
import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..auth.utils import get_password_hash
from ..database import get_db
from ..services.image_service import optimize_image
from ..services.s3_service import (
    delete_file_from_s3,
    extract_object_name_from_url,
    upload_file_to_s3,
)

router = APIRouter(prefix="/users", tags=["users"])


def _user_to_dict(user: models.User) -> dict:
    props = user.properties or {}
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "is_verified": user.is_verified,
        "is_guest": user.is_guest,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "bio": props.get("bio"),
        "social_links": props.get("social_links"),
    }


@router.get("/me", response_model=models.UserRead)
async def get_current_user(user: models.User = Depends(current_active_user)):
    return _user_to_dict(user)


@router.patch("/me", response_model=models.UserRead)
async def update_current_user(
    user_update: models.UserUpdate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    update_data = user_update.model_dump(exclude_unset=True)

    bio = update_data.pop("bio", None)
    social_links = update_data.pop("social_links", None)
    needs_properties_update = (
        "bio" in user_update.model_fields_set
        or "social_links" in user_update.model_fields_set
    )

    if needs_properties_update:
        current_props = dict(user.properties) if user.properties else {}
        if "bio" in user_update.model_fields_set:
            current_props["bio"] = bio
        if "social_links" in user_update.model_fields_set:
            current_props["social_links"] = (
                {k: v for k, v in social_links.items() if v is not None}
                if social_links
                else None
            )
        user.properties = current_props

    for key, value in update_data.items():
        if key == "password" and value:
            user.hashed_password = get_password_hash(value)
        else:
            setattr(user, key, value)

    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return _user_to_dict(user)
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="USERNAME_ALREADY_EXISTS",
        )


@router.post("/me/avatar", response_model=models.UserRead)
async def upload_avatar(
    file: fastapi.UploadFile = fastapi.File(...),
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.content_type.startswith("image/"):
        raise fastapi.HTTPException(status_code=400, detail="File must be an image")

    try:
        contents = await file.read()

        # Optimize image in a separate thread
        optimized_bytes = await asyncio.to_thread(optimize_image, contents)

        # Delete old avatar if it exists
        if user.avatar_url:
            old_object_name = extract_object_name_from_url(user.avatar_url)
            if old_object_name:
                await asyncio.to_thread(delete_file_from_s3, old_object_name)

        # Upload to S3
        file_extension = "webp"
        object_name = f"avatars/{user.id}/{uuid.uuid4()}.{file_extension}"
        avatar_url = await asyncio.to_thread(
            upload_file_to_s3, optimized_bytes, object_name, "image/webp"
        )

        # Update user
        user.avatar_url = avatar_url
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return _user_to_dict(user)
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))


@router.delete("/me/avatar", response_model=models.UserRead)
async def remove_avatar(
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if user.avatar_url:
        old_object_name = extract_object_name_from_url(user.avatar_url)
        if old_object_name:
            await asyncio.to_thread(delete_file_from_s3, old_object_name)

        user.avatar_url = None
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return _user_to_dict(user)


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
    return _user_to_dict(user)


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
