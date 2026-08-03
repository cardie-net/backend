import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from . import models


async def is_slug_taken(
    db: AsyncSession,
    user_id: uuid.UUID | str,
    slug: str,
    exclude_id: uuid.UUID | str | None = None,
) -> bool:
    """Check if a slug is taken by any deck or folder belonging to user_id."""
    stmt_deck = select(models.Deck.id).where(
        models.Deck.user_id == user_id, models.Deck.slug == slug
    )
    if exclude_id:
        stmt_deck = stmt_deck.where(models.Deck.id != exclude_id)
    res_deck = await db.execute(stmt_deck)
    if res_deck.scalars().first() is not None:
        return True

    stmt_folder = select(models.Folder.id).where(
        models.Folder.user_id == user_id, models.Folder.slug == slug
    )
    if exclude_id:
        stmt_folder = stmt_folder.where(models.Folder.id != exclude_id)
    res_folder = await db.execute(stmt_folder)
    if res_folder.scalars().first() is not None:
        return True

    return False


async def generate_unique_slug(
    db: AsyncSession,
    model: type | None,
    user_id: uuid.UUID | str,
    name: str,
    max_length: int = 80,
    exclude_id: uuid.UUID | str | None = None,
) -> str:
    """
    Generate a unique slug across Decks and Folders for a given user, based on the provided name.
    Ensures length is between 1 and max_length, only url-safe characters, and uniqueness for the user.
    """
    # 1. Base generation
    base_slug = re.sub(r"[^a-zA-Z0-9_-]", "", name.lower())

    # Fallback if empty or all invalid chars
    if not base_slug:
        base_slug = model.__name__.lower() if model else "item"

    # Cut off if too long
    truncate_len = max(1, max_length - 10)
    base_slug = base_slug[:truncate_len]

    target_model = model or models.Deck
    stmt = select(target_model.slug).where(
        target_model.user_id == user_id, target_model.slug.like(f"{base_slug}%")
    )

    res = await db.execute(stmt)
    existing_slugs = set(res.scalars().all())

    if target_model == models.Deck:
        try:
            res2 = await db.execute(
                select(models.Folder.slug).where(
                    models.Folder.user_id == user_id,
                    models.Folder.slug.like(f"{base_slug}%"),
                )
            )
            existing_slugs.update(res2.scalars().all())
        except Exception:
            pass
    elif target_model == models.Folder:
        try:
            res2 = await db.execute(
                select(models.Deck.slug).where(
                    models.Deck.user_id == user_id,
                    models.Deck.slug.like(f"{base_slug}%"),
                )
            )
            existing_slugs.update(res2.scalars().all())
        except Exception:
            pass

    if base_slug not in existing_slugs:
        if len(base_slug) > max_length:
            raise ValueError(
                f"Cannot generate a unique slug within the {max_length} character limit."
            )
        return base_slug

    # 2. Handle collisions
    counter = 1
    new_slug = f"{base_slug}-{counter}"

    while new_slug in existing_slugs:
        if len(new_slug) > max_length:
            raise ValueError(
                f"Cannot generate a unique slug within the {max_length} character limit."
            )
        counter += 1
        new_slug = f"{base_slug}-{counter}"

    if len(new_slug) > max_length:
        raise ValueError(
            f"Cannot generate a unique slug within the {max_length} character limit."
        )

    return new_slug
