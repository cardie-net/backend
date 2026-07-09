from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..database import get_db

router = APIRouter(prefix="/decks/{deck_id}/cards", tags=["cards"])


@router.get("/", response_model=List[models.CardRead])
async def read_cards(
    deck_id: int,
    skip: int = 0,
    limit: int = 100,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id and deck.privacy == models.PrivacyLevel.private:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return await crud.get_cards_for_deck(db, deck_id=deck_id, skip=skip, limit=limit)


@router.post("/", response_model=models.CardRead)
async def create_card(
    deck_id: int,
    card: models.CardCreate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return await crud.create_card_for_deck(db=db, card=card, deck_id=deck_id)
