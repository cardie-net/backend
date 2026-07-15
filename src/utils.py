import re
from typing import Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

T = TypeVar("T", bound=SQLModel)


async def generate_unique_slug(
    db: AsyncSession, model: Type[T], user_id: str, name: str, max_length: int = 80
) -> str:
    """
    Generate a unique slug for a given model (e.g. Deck, Folder) and user, based on the provided name.
    Ensures length is between 8 and max_length, only url-safe characters, and uniqueness for the user.
    """
    # 1. Base generation
    # Strip non-url-safe characters, keep only alphanum, dash, underscore
    base_slug = re.sub(r"[^a-zA-Z0-9_-]", "", name.lower())

    # Fallback if empty or all invalid chars
    if not base_slug:
        base_slug = model.__name__.lower()

    # Cut off if too long (leave room for padding and uniqueness counter)
    truncate_len = max(8, max_length - 10)
    base_slug = base_slug[:truncate_len]

    # Pad if too short
    if len(base_slug) < 8:
        base_slug = base_slug.ljust(8, "0")

    # Check uniqueness
    statement = select(model.slug).where(
        model.user_id == user_id, model.slug.like(f"{base_slug}%")
    )
    result = await db.execute(statement)
    existing_slugs = set(result.scalars().all())

    if base_slug not in existing_slugs:
        if len(base_slug) > max_length:
            raise ValueError(
                f"Cannot generate a unique slug within the {max_length} character limit."
            )
        return base_slug

    # 2. Handle collisions
    counter = 1
    new_slug = f"{base_slug}-{counter}"
    if len(new_slug) > max_length:
        raise ValueError(
            f"Cannot generate a unique slug within the {max_length} character limit."
        )

    while new_slug in existing_slugs:
        counter += 1
        new_slug = f"{base_slug}-{counter}"
        if len(new_slug) > max_length:
            raise ValueError(
                f"Cannot generate a unique slug within the {max_length} character limit."
            )

    return new_slug
