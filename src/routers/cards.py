import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..database import get_db

router = APIRouter(prefix="/decks/{deck_id}/cards", tags=["cards"])


@router.get("/", response_model=List[models.CardRead])
async def read_cards(
    deck_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id and deck.privacy == models.PrivacyLevel.PRIVATE:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return await crud.get_cards_for_deck(db, deck_id=deck_id)


@router.post("/", response_model=models.CardRead)
async def create_card(
    deck_id: uuid.UUID,
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


@router.delete("/{card_id}", status_code=204)
async def delete_card(
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    card = await crud.get_card(db, card_id=card_id)
    if not card or card.deck_id != deck_id:
        raise HTTPException(status_code=404, detail="Card not found")

    await crud.delete_card(db, db_card=card)


@router.patch("/{card_id}", response_model=models.CardRead)
async def update_card(
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    card_update: models.CardUpdate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    card = await crud.get_card(db, card_id=card_id)
    if not card or card.deck_id != deck_id:
        raise HTTPException(status_code=404, detail="Card not found")

    return await crud.update_card(db, db_card=card, card_update=card_update)


@router.post("/reorder")
async def reorder_cards(
    deck_id: uuid.UUID,
    reorder: models.CardReorder,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    current_cards = await crud.get_cards_for_deck(db, deck_id=deck_id)
    current_card_ids = {c.id for c in current_cards}

    if len(reorder.card_ids) != len(set(reorder.card_ids)):
        raise HTTPException(status_code=400, detail="Duplicate card IDs provided")

    if set(reorder.card_ids) != current_card_ids:
        raise HTTPException(
            status_code=400,
            detail="Provided card IDs do not match the deck's cards exactly",
        )

    await crud.reorder_cards(db, deck_id=deck_id, card_ids=reorder.card_ids)
    return {"status": "ok"}
