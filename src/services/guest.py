import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models import Deck


async def transfer_guest_data(
    guest_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
    session: AsyncSession,
) -> int:
    """Transfer all decks (and their cards) from a guest user to the target user.

    Returns the number of decks transferred.
    """
    statement = select(Deck).where(Deck.user_id == guest_user_id)
    result = await session.execute(statement)
    decks = result.scalars().all()

    for deck in decks:
        deck.user_id = target_user_id

    await session.commit()
    return len(decks)
