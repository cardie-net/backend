import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.schemas import CardProgressUpdate
from ..models.tables import CardProgress


async def get_deck_progress(
    db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID
) -> list[CardProgress]:
    """Get the learning progress for a specific user and deck."""
    # We join with cards to ensure the progress we return belongs to the deck.
    # Wait, the deck_id is no longer on CardProgress. We just need to get progress for cards in the deck.
    from ..models.tables import Card

    query = (
        select(CardProgress)
        .join(Card, CardProgress.card_id == Card.id)
        .where(CardProgress.user_id == user_id, Card.deck_id == deck_id)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def sync_deck_progress(
    db: AsyncSession,
    user_id: uuid.UUID,
    deck_id: uuid.UUID,
    progress_updates: list[CardProgressUpdate],
) -> None:
    """Sync a batch of card progress updates for a user."""
    from ..models.tables import Card

    # Extract the requested card_ids
    card_ids = [p.card_id for p in progress_updates]
    if not card_ids:
        return

    # Make sure all card_ids actually belong to the deck
    query_cards = select(Card).where(Card.deck_id == deck_id, Card.id.in_(card_ids))
    valid_cards_result = await db.execute(query_cards)
    valid_card_ids = {c.id for c in valid_cards_result.scalars().all()}

    # Filter out invalid updates and deduplicate (keep latest)
    valid_updates_map = {}
    for p in progress_updates:
        if p.card_id in valid_card_ids:
            valid_updates_map[p.card_id] = p
    valid_updates = list(valid_updates_map.values())

    if not valid_updates:
        return

    # Get existing progress rows
    query_existing = select(CardProgress).where(
        CardProgress.user_id == user_id, CardProgress.card_id.in_(valid_card_ids)
    )
    existing_result = await db.execute(query_existing)
    existing_progress = {p.card_id: p for p in existing_result.scalars().all()}

    # Also keep track of newly created rows in this session to prevent duplicate adds
    newly_added = {}

    for update in valid_updates:
        if update.card_id in existing_progress:
            if update.box == 1:
                await db.delete(existing_progress[update.card_id])
            else:
                existing_progress[update.card_id].box = update.box
        elif update.card_id in newly_added:
            if update.box == 1:
                db.expunge(newly_added[update.card_id])
                del newly_added[update.card_id]
            else:
                newly_added[update.card_id].box = update.box
        else:
            # Create new row if box > 1
            if update.box > 1:
                new_progress = CardProgress(
                    user_id=user_id,
                    card_id=update.card_id,
                    box=update.box,
                )
                db.add(new_progress)
                newly_added[update.card_id] = new_progress

    await db.commit()
