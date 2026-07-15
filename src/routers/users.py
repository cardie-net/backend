import asyncio
import uuid
from typing import Dict, List, Optional, Union

import fastapi
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..auth.user_manager import UserManager, get_user_manager
from ..database import get_db
from ..services.image_service import optimize_image
from ..services.s3_service import (
    delete_file_from_s3,
    extract_object_name_from_url,
    upload_file_to_s3,
)

router = APIRouter(prefix="/users", tags=["users"])


def _user_read_with_properties(user: models.User) -> dict:
    """Build a UserRead-compatible dict that includes bio and social_links
    extracted from the user's properties JSON column."""
    props = user.properties or {}
    data = {
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
    return data


@router.get("/me", response_model=models.UserRead)
async def get_current_user(user: models.User = Depends(current_active_user)):
    return _user_read_with_properties(user)


@router.patch("/me", response_model=models.UserRead)
async def update_current_user(
    user_update: models.UserUpdate,
    user: models.User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    # Extract bio and social_links before passing to fastapi-users
    bio = user_update.bio
    social_links = user_update.social_links

    needs_properties_update = bio is not None or social_links is not None

    if needs_properties_update:
        current_props = dict(user.properties) if user.properties else {}
        if bio is not None:
            current_props["bio"] = bio
        if social_links is not None:
            # Store as a plain dict (only non-None values)
            current_props["social_links"] = {
                k: v for k, v in social_links.model_dump().items() if v is not None
            }

        # Directly update properties on the user object
        user.properties = current_props
        session = user_manager.user_db.session
        session.add(user)
        await session.commit()
        await session.refresh(user)

    # Build a clean UserUpdate without bio/social_links for fastapi-users
    update_dict = user_update.model_dump(exclude_unset=True)
    update_dict.pop("bio", None)
    update_dict.pop("social_links", None)
    clean_update = models.UserUpdate(**update_dict)

    try:
        user = await user_manager.update(clean_update, user, safe=True)
        return _user_read_with_properties(user)
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
        user_update = models.UserUpdate(avatar_url=avatar_url)
        user = await user_manager.update(user_update, user, safe=True)

        return _user_read_with_properties(user)
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))


@router.delete("/me/avatar", response_model=models.UserRead)
async def remove_avatar(
    user: models.User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    if user.avatar_url:
        old_object_name = extract_object_name_from_url(user.avatar_url)
        if old_object_name:
            await asyncio.to_thread(delete_file_from_s3, old_object_name)

        user_update = models.UserUpdate(avatar_url=None)
        # Using safe=False or safe=True depending on if fastapi-users allows None.
        # But wait, fastapi-users Pydantic models with `None` might ignore the update if unset.
        # So we create dict explicitly if needed, but user_update(avatar_url=None) is fine.
        user = await user_manager.update(user_update, user, safe=True)
    return _user_read_with_properties(user)


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
    return _user_read_with_properties(user)


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
