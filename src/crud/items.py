import uuid
from typing import List, Union

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from .. import models
from .folder import get_folder


async def get_folder_items_recursive(
    db: AsyncSession, folder_id: uuid.UUID, requesting_user_id: uuid.UUID
) -> List[Union[models.Folder, models.Deck]]:
    # We need to fetch the initial folder to check permissions
    folder = await get_folder(db, folder_id=folder_id)

    if not folder:
        return None

    is_owner = folder.user_id == requesting_user_id
    if not is_owner and folder.privacy == models.PrivacyLevel.PRIVATE:
        return None

    items = []

    # helper for recursive fetch
    async def fetch_children(current_folder, owner_access):
        # Add current folder's decks
        for d in current_folder.decks:
            if owner_access or d.privacy in (
                models.PrivacyLevel.PUBLIC,
                models.PrivacyLevel.UNLISTED,
            ):
                items.append(d)

        # Add current folder's child folders
        for f in current_folder.child_folders:
            if owner_access or f.privacy in (
                models.PrivacyLevel.PUBLIC,
                models.PrivacyLevel.UNLISTED,
            ):
                items.append(f)

                # Fetch children of this child folder
                full_f = await get_folder(db, folder_id=f.id)
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
            models.PrivacyLevel.PUBLIC,
            models.PrivacyLevel.UNLISTED,
        ):
            items.append(f)
    for d in decks:
        if is_owner or d.privacy in (
            models.PrivacyLevel.PUBLIC,
            models.PrivacyLevel.UNLISTED,
        ):
            items.append(d)

    return items
