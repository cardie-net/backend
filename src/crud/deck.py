import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from .. import models
from ..utils import generate_unique_slug


async def get_decks_for_user(
    db: AsyncSession, user_id: uuid.UUID, skip: int = 0, limit: int = 100
):
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
):
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


async def get_deck(db: AsyncSession, deck_id: uuid.UUID):
    return await db.get(models.Deck, deck_id)


async def delete_deck(db: AsyncSession, db_deck: models.Deck):
    await db.delete(db_deck)
    await db.commit()


async def update_deck(
    db: AsyncSession, db_deck: models.Deck, deck_update: models.DeckUpdate
):
    update_data = deck_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_deck, key, value)
    db.add(db_deck)
    await db.commit()
    await db.refresh(db_deck)
    return db_deck
