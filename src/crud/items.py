import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from .. import models
from .folder import get_folder


async def get_folder_items_recursive(
    db: AsyncSession, folder_id: uuid.UUID, requesting_user_id: uuid.UUID
) -> list[models.Folder | models.Deck] | None:
    """Recursively fetch all items in a folder, respecting privacy."""
    folder = await get_folder(db, folder_id=folder_id)

    if not folder:
        return None

    is_owner = folder.user_id == requesting_user_id
    if not is_owner and folder.privacy == models.PrivacyLevel.PRIVATE:
        return None

    items: list[models.Folder | models.Deck] = []
    visited: set[uuid.UUID] = set()

    async def fetch_children(current_folder: models.Folder, owner_access: bool) -> None:
        visited.add(current_folder.id)

        for d in current_folder.decks:
            if owner_access or d.privacy == models.PrivacyLevel.PUBLIC:
                items.append(d)

        for f in current_folder.child_folders:
            if f.id in visited:
                continue
            if owner_access or f.privacy == models.PrivacyLevel.PUBLIC:
                items.append(f)

                full_f = await get_folder(db, folder_id=f.id)
                if full_f:
                    await fetch_children(full_f, owner_access)

    await fetch_children(folder, is_owner)
    return items


async def get_user_items(
    db: AsyncSession, target_user_id: uuid.UUID, requesting_user_id: uuid.UUID
) -> list[models.Folder | models.Deck]:
    """Fetch all top-level items for a user, respecting privacy."""
    is_owner = target_user_id == requesting_user_id

    stmt_folders = select(models.Folder).where(models.Folder.user_id == target_user_id)
    res_folders = await db.execute(stmt_folders)
    folders = res_folders.scalars().all()

    stmt_decks = select(models.Deck).where(models.Deck.user_id == target_user_id)
    res_decks = await db.execute(stmt_decks)
    decks = res_decks.scalars().all()

    items: list[models.Folder | models.Deck] = []
    for f in folders:
        if is_owner or f.privacy == models.PrivacyLevel.PUBLIC:
            items.append(f)
    for d in decks:
        if is_owner or d.privacy == models.PrivacyLevel.PUBLIC:
            items.append(d)

    return items
