import uuid
from typing import List, Union

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from .. import models


async def get_folder_items_recursive(
    db: AsyncSession, folder_id: int, requesting_user_id: uuid.UUID
) -> List[Union[models.Folder, models.Deck]]:
    # We need to fetch the initial folder to check permissions
    statement = (
        select(models.Folder)
        .where(models.Folder.id == folder_id)
        .options(
            selectinload(models.Folder.child_folders),
            selectinload(models.Folder.decks),
        )
    )
    result = await db.execute(statement)
    folder = result.scalars().first()

    if not folder:
        return None

    is_owner = folder.user_id == requesting_user_id
    if not is_owner and folder.privacy == models.PrivacyLevel.private:
        return None

    items = []

    # helper for recursive fetch
    async def fetch_children(current_folder, owner_access):
        # Add current folder's decks
        for d in current_folder.decks:
            if owner_access or d.privacy in (
                models.PrivacyLevel.public,
                models.PrivacyLevel.unlisted,
            ):
                items.append(d)

        # Add current folder's child folders
        for f in current_folder.child_folders:
            if owner_access or f.privacy in (
                models.PrivacyLevel.public,
                models.PrivacyLevel.unlisted,
            ):
                items.append(f)

                # Fetch children of this child folder
                stmt = (
                    select(models.Folder)
                    .where(models.Folder.id == f.id)
                    .options(
                        selectinload(models.Folder.child_folders),
                        selectinload(models.Folder.decks),
                    )
                )
                res = await db.execute(stmt)
                full_f = res.scalars().first()
                if full_f:
                    await fetch_children(full_f, owner_access)

    await fetch_children(folder, is_owner)
    return items


async def get_user_items(
    db: AsyncSession, target_user_id: uuid.UUID, requesting_user_id: uuid.UUID
) -> List[Union[models.Folder, models.Deck]]:
    is_owner = target_user_id == requesting_user_id

    # Fetch all folders of the user
    stmt_folders = select(models.Folder).where(models.Folder.user_id == target_user_id)
    res_folders = await db.execute(stmt_folders)
    folders = res_folders.scalars().all()

    # Fetch all decks of the user
    stmt_decks = select(models.Deck).where(models.Deck.user_id == target_user_id)
    res_decks = await db.execute(stmt_decks)
    decks = res_decks.scalars().all()

    items = []
    for f in folders:
        if is_owner or f.privacy in (
            models.PrivacyLevel.public,
            models.PrivacyLevel.unlisted,
        ):
            items.append(f)
    for d in decks:
        if is_owner or d.privacy in (
            models.PrivacyLevel.public,
            models.PrivacyLevel.unlisted,
        ):
            items.append(d)

    return items
