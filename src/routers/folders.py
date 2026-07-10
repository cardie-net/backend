from typing import List

import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..database import get_db

router = APIRouter(prefix="/folders", tags=["folders"])


@router.post("/", response_model=models.FolderRead)
async def create_folder(
    folder: models.FolderCreate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if folder.parent_id is not None:
        parent_folder = await crud.get_folder(db, folder_id=folder.parent_id)
        if not parent_folder:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        if parent_folder.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not enough permissions")

    try:
        return await crud.create_folder_for_user(db=db, folder=folder, user_id=user.id)
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="Folder with this slug already exists"
        )


@router.get("/{folder_id}", response_model=models.FolderWithContents)
async def get_folder(
    folder_id: int,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    folder = await crud.get_folder(db, folder_id=folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    is_owner = folder.user_id == user.id

    if not is_owner and folder.privacy == models.PrivacyLevel.private:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Filter contents based on privacy if not owner
    if not is_owner:
        visible_decks = [
            d
            for d in folder.decks
            if d.privacy in (models.PrivacyLevel.public, models.PrivacyLevel.unlisted)
        ]
        visible_folders = [
            f
            for f in folder.child_folders
            if f.privacy in (models.PrivacyLevel.public, models.PrivacyLevel.unlisted)
        ]
    else:
        visible_decks = folder.decks
        visible_folders = folder.child_folders

    return models.FolderWithContents(
        id=folder.id,
        name=folder.name,
        slug=folder.slug,
        privacy=folder.privacy,
        user_id=folder.user_id,
        parent_id=folder.parent_id,
        decks=visible_decks,
        folders=visible_folders,
    )
