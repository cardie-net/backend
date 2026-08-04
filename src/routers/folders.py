import asyncio
import logging
import uuid

import fastapi
import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..auth.utils import get_optional_current_user
from ..config import settings
from ..database import get_db
from ..services.image_service import collect_image_urls, optimize_image
from ..services.s3_service import (
    CARD_IMAGE_PREFIX,
    COVER_IMAGE_PREFIX,
    delete_file_from_s3,
    delete_managed_images,
    extract_object_name_from_url,
    upload_file_to_s3,
)
from ..utils import is_slug_taken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/folders", tags=["folders"])


@router.post("", response_model=models.FolderRead)
async def create_folder(
    folder: models.FolderCreate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> models.FolderRead:
    """Create a new folder for the current user."""
    if folder.parent_id is not None:
        parent_folder = await crud.get_folder(db, folder_id=folder.parent_id)
        if not parent_folder:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        if parent_folder.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not enough permissions")

    if folder.slug and await is_slug_taken(db, user_id=user.id, slug=folder.slug):
        raise HTTPException(
            status_code=400, detail="Folder or deck with this slug already exists"
        )

    try:
        return await crud.create_folder_for_user(db=db, folder=folder, user_id=user.id)
    except sqlalchemy.exc.IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="Folder or deck with this slug already exists"
        ) from exc


@router.post("/{folder_id}/cover", response_model=models.FolderRead)
async def upload_folder_cover(
    folder_id: uuid.UUID,
    file: fastapi.UploadFile = fastapi.File(...),
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> models.FolderRead:
    """Upload a cover image for a folder."""
    db_folder = await crud.get_folder(db, folder_id=folder_id)
    if not db_folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if db_folder.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        contents = await file.read(settings.MAX_UPLOAD_SIZE + 1)
        if len(contents) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large")

        optimized_bytes = await asyncio.to_thread(optimize_image, contents)

        old_cover = (
            db_folder.properties.get("cover_image_url")
            if db_folder.properties
            else None
        )

        object_name = f"{COVER_IMAGE_PREFIX}{user.id}/{folder_id}/{uuid.uuid4()}.webp"
        image_url = await asyncio.to_thread(
            upload_file_to_s3, optimized_bytes, object_name, "image/webp"
        )

        properties = dict(db_folder.properties) if db_folder.properties else {}
        properties["cover_image_url"] = image_url
        folder_update = models.FolderUpdate(
            properties=models.ItemProperties(**properties)
        )
        updated_folder = await crud.update_folder(
            db=db, folder_id=folder_id, folder_update=folder_update
        )

        if old_cover:
            old_cover_obj = extract_object_name_from_url(old_cover, COVER_IMAGE_PREFIX)
            if old_cover_obj:
                await asyncio.to_thread(delete_file_from_s3, old_cover_obj)

        return updated_folder
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload folder cover: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload image")


@router.get("/{folder_id}", response_model=models.FolderRead)
async def get_folder(
    folder_id: uuid.UUID,
    user: models.User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> models.FolderRead:
    """Retrieve a specific folder by ID."""
    db_folder = await crud.get_folder(db, folder_id=folder_id)
    if not db_folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    user_id = user.id if user else None
    if (
        db_folder.user_id != user_id
        and db_folder.privacy == models.PrivacyLevel.PRIVATE
    ):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return db_folder


@router.get(
    "/{folder_id}/items", response_model=list[models.FolderRead | models.DeckRead]
)
async def get_folder_items(
    folder_id: uuid.UUID,
    user: models.User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[models.FolderRead | models.DeckRead]:
    """Retrieve all items within a specific folder."""
    requesting_user_id = user.id if user else None
    items = await crud.get_folder_items_recursive(
        db, folder_id=folder_id, requesting_user_id=requesting_user_id
    )
    if items is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return items


@router.patch("/{folder_id}", response_model=models.FolderRead)
async def update_folder(
    folder_id: uuid.UUID,
    folder_update: models.FolderUpdate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> models.FolderRead:
    """Update properties of a specific folder."""
    db_folder = await crud.get_folder(db, folder_id=folder_id)
    if not db_folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if db_folder.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    if folder_update.parent_id is not None:
        parent_folder = await crud.get_folder(db, folder_id=folder_update.parent_id)
        if not parent_folder:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        if parent_folder.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not enough permissions")

    if folder_update.slug is not None and await is_slug_taken(
        db, user_id=user.id, slug=folder_update.slug, exclude_id=folder_id
    ):
        raise HTTPException(
            status_code=400, detail="Folder or deck with this slug already exists"
        )

    try:
        old_cover = (
            db_folder.properties.get("cover_image_url")
            if db_folder.properties
            else None
        )

        updated_folder = await crud.update_folder(
            db=db, folder_id=folder_id, folder_update=folder_update
        )

        new_cover = (
            updated_folder.properties.get("cover_image_url")
            if updated_folder.properties
            else None
        )
        if old_cover and old_cover != new_cover:
            old_cover_obj = extract_object_name_from_url(old_cover, COVER_IMAGE_PREFIX)
            if old_cover_obj:
                await asyncio.to_thread(delete_file_from_s3, old_cover_obj)

        return updated_folder
    except sqlalchemy.exc.IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="Folder or deck with this slug already exists"
        ) from exc


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a specific folder and its contents."""
    db_folder = await crud.get_folder(db, folder_id=folder_id)
    if not db_folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if db_folder.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Gather items before deleting
    items = await crud.get_folder_items_recursive(
        db, folder_id=folder_id, requesting_user_id=user.id
    )
    cover_urls = []
    card_urls = []

    if db_folder.properties and db_folder.properties.get("cover_image_url"):
        cover_urls.append(db_folder.properties["cover_image_url"])

    if items:
        for item in items:
            if item.properties and item.properties.get("cover_image_url"):
                cover_urls.append(item.properties["cover_image_url"])
            if getattr(item, "type", None) == "deck":
                deck_cards = await crud.get_cards_for_deck(db, deck_id=item.id)
                for card in deck_cards:
                    card_urls.extend(collect_image_urls(card.front, card.back))

    success = await crud.delete_folder(db, folder_id=folder_id)
    if not success:
        raise HTTPException(status_code=404, detail="Folder not found")

    if cover_urls:
        await asyncio.to_thread(delete_managed_images, cover_urls, COVER_IMAGE_PREFIX)
    if card_urls:
        await asyncio.to_thread(
            delete_managed_images, card_urls, f"{CARD_IMAGE_PREFIX}{user.id}/"
        )

    return None
