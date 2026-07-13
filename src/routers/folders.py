import uuid
from typing import List, Union

import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..database import get_db

router = APIRouter(prefix="/folders", tags=["folders"])


@router.post("", response_model=models.FolderRead)
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
    except sqlalchemy.exc.IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="Folder with this slug already exists"
        ) from exc


@router.get(
    "/{folder_id}/items", response_model=List[Union[models.FolderRead, models.DeckRead]]
)
async def get_folder_items(
    folder_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    items = await crud.get_folder_items_recursive(
        db, folder_id=folder_id, requesting_user_id=user.id
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
):
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

    try:
        updated_folder = await crud.update_folder(
            db=db, folder_id=folder_id, folder_update=folder_update
        )
        return updated_folder
    except sqlalchemy.exc.IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="Folder with this slug already exists"
        ) from exc


@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    db_folder = await crud.get_folder(db, folder_id=folder_id)
    if not db_folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if db_folder.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    success = await crud.delete_folder(db, folder_id=folder_id)
    if not success:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}
