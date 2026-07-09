import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from . import models


# Deck
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
    db_deck = models.Deck(**deck.model_dump(), user_id=user_id)
    db.add(db_deck)
    await db.commit()
    await db.refresh(db_deck)
    return db_deck


# Card
async def get_cards_for_deck(
    db: AsyncSession, deck_id: int, skip: int = 0, limit: int = 100
):
    statement = (
        select(models.Card)
        .where(models.Card.deck_id == deck_id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(statement)
    return result.scalars().all()


async def create_card_for_deck(db: AsyncSession, card: models.CardCreate, deck_id: int):
    db_card = models.Card(**card.model_dump(), deck_id=deck_id)
    db.add(db_card)
    await db.commit()
    await db.refresh(db_card)
    return db_card
