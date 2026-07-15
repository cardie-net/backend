import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from .. import models
from ..utils import generate_unique_slug


async def get_folders_for_user(
    db: AsyncSession, user_id: uuid.UUID, skip: int = 0, limit: int = 100
):
    statement = (
        select(models.Folder)
        .where(models.Folder.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(statement)
    return result.scalars().all()


async def create_folder_for_user(
    db: AsyncSession, folder: models.FolderCreate, user_id: uuid.UUID
):
    folder_data = folder.model_dump()
    if not folder_data.get("slug"):
        folder_data["slug"] = await generate_unique_slug(
            db, models.Folder, user_id, folder.name
        )
    db_folder = models.Folder(**folder_data, user_id=user_id)
    db.add(db_folder)
    await db.commit()
    await db.refresh(db_folder)
    return db_folder


async def get_folder(db: AsyncSession, folder_id: uuid.UUID):
    # Using select with selectinload for child_folders and decks
    statement = (
        select(models.Folder)
        .where(models.Folder.id == folder_id)
        .options(
            selectinload(models.Folder.child_folders),
            selectinload(models.Folder.decks),
        )
    )
    result = await db.execute(statement)
    return result.scalars().first()


async def update_folder(
    db: AsyncSession, folder_id: uuid.UUID, folder_update: models.FolderUpdate
):
    db_folder = await get_folder(db, folder_id=folder_id)
    if not db_folder:
        return None

    update_data = folder_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_folder, key, value)

    db.add(db_folder)
    await db.commit()
    await db.refresh(db_folder)
    return db_folder


async def delete_folder(db: AsyncSession, folder_id: uuid.UUID):
    db_folder = await get_folder(db, folder_id=folder_id)
    if not db_folder:
        return False
    await db.delete(db_folder)
    await db.commit()
    return True
