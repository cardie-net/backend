import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from .. import models
from ..utils import generate_unique_slug


async def get_decks_for_user(
    db: AsyncSession, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> list[models.Deck]:
    """Retrieve decks owned by a specific user."""
    statement = (
        select(models.Deck)
        .where(models.Deck.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(statement)
    return result.scalars().all()


async def create_deck_for_user(
    db: AsyncSession, deck: models.DeckCreate, user_id: uuid.UUID
) -> models.Deck:
    """Create a new deck for the specified user."""
    deck_data = deck.model_dump()
    if not deck_data.get("slug"):
        deck_data["slug"] = await generate_unique_slug(
            db, models.Deck, user_id, deck.name
        )
    db_deck = models.Deck(**deck_data, user_id=user_id)
    db.add(db_deck)
    await db.commit()
    await db.refresh(db_deck)
    return db_deck


async def get_deck(db: AsyncSession, deck_id: uuid.UUID) -> models.Deck | None:
    """Retrieve a specific deck by ID."""
    return await db.get(models.Deck, deck_id)


async def get_deck_by_username_and_slug(
    db: AsyncSession, username: str, slug: str
) -> models.Deck | None:
    """Retrieve a deck by its owner's username and the deck's slug."""
    statement = (
        select(models.Deck)
        .join(models.User, models.Deck.user_id == models.User.id)
        .where(models.User.username == username, models.Deck.slug == slug)
    )
    result = await db.execute(statement)
    return result.scalars().first()


async def delete_deck(db: AsyncSession, db_deck: models.Deck) -> None:
    """Delete a specific deck."""
    await db.delete(db_deck)
    await db.commit()


async def update_deck(
    db: AsyncSession, db_deck: models.Deck, deck_update: models.DeckUpdate
) -> models.Deck:
    """Update properties of a specific deck."""
    update_data = deck_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "properties" and isinstance(value, dict) and db_deck.properties:
            # Merge the new properties into the existing ones
            merged_properties = dict(db_deck.properties)
            merged_properties.update(value)
            setattr(db_deck, key, merged_properties)
            flag_modified(db_deck, "properties")
        else:
            setattr(db_deck, key, value)
    db.add(db_deck)
    await db.commit()
    await db.refresh(db_deck)
    return db_deck


async def get_deck_match_time(
    db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID
) -> models.DeckMatchTime | None:
    statement = select(models.DeckMatchTime).where(
        models.DeckMatchTime.user_id == user_id,
        models.DeckMatchTime.deck_id == deck_id,
    )
    result = await db.execute(statement)
    return result.scalars().first()


async def update_deck_match_time(
    db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID, time_ms: int
) -> models.DeckMatchTime:
    match_time = await get_deck_match_time(db, user_id, deck_id)
    if not match_time:
        match_time = models.DeckMatchTime(
            user_id=user_id, deck_id=deck_id, best_time_ms=time_ms
        )
        db.add(match_time)
    elif time_ms < match_time.best_time_ms:
        match_time.best_time_ms = time_ms
        db.add(match_time)
    await db.commit()
    await db.refresh(match_time)
    return match_time


async def clear_deck_match_time(
    db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID
) -> None:
    match_time = await get_deck_match_time(db, user_id, deck_id)
    if match_time:
        await db.delete(match_time)
        await db.commit()
