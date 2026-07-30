import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from .. import models


async def get_card(db: AsyncSession, card_id: uuid.UUID) -> models.Card | None:
    """Retrieve a specific card by ID."""
    statement = select(models.Card).where(models.Card.id == card_id)
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def get_cards_for_deck(db: AsyncSession, deck_id: uuid.UUID) -> list[models.Card]:
    """Retrieve all cards within a deck, ordered sequentially."""
    statement = (
        select(models.Card)
        .where(models.Card.deck_id == deck_id)
        .order_by(models.Card.order.asc())  # pylint: disable=no-member
    )
    result = await db.execute(statement)
    return result.scalars().all()


async def create_card_for_deck(
    db: AsyncSession, card: models.CardCreate, deck_id: uuid.UUID
) -> models.Card:
    """Create a new card and append it to the end of the deck."""
    statement = select(func.max(models.Card.order)).where(
        models.Card.deck_id == deck_id
    )
    result = await db.execute(statement)
    max_order = result.scalar()
    next_order = (max_order + 1) if max_order is not None else 0

    card_dict = card.model_dump()
    card_dict["order"] = next_order
    db_card = models.Card(**card_dict, deck_id=deck_id)
    db.add(db_card)
    await db.commit()
    await db.refresh(db_card)
    return db_card


async def update_card(
    db: AsyncSession, db_card: models.Card, card_update: models.CardUpdate
) -> models.Card:
    """Update properties of an existing card."""
    update_data = card_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_card, key, value)

    db.add(db_card)
    await db.commit()
    await db.refresh(db_card)
    return db_card


async def delete_card(db: AsyncSession, db_card: models.Card) -> None:
    """Delete a specific card."""
    await db.delete(db_card)
    await db.commit()


async def reorder_cards(
    db: AsyncSession, deck_id: uuid.UUID, card_ids: list[uuid.UUID]
) -> None:
    """Update the sequential order of cards in a deck."""
    statement = select(models.Card).where(models.Card.deck_id == deck_id)
    result = await db.execute(statement)
    cards = {c.id: c for c in result.scalars().all()}

    for order, card_id in enumerate(card_ids):
        if card_id in cards:
            cards[card_id].order = order
            db.add(cards[card_id])

    await db.commit()
