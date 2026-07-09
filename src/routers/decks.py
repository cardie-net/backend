from typing import List

import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..database import get_db

router = APIRouter(prefix="/decks", tags=["decks"])


@router.get("/", response_model=List[models.DeckRead])
async def read_my_decks(
    skip: int = 0,
    limit: int = 100,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_decks_for_user(db, user_id=user.id, skip=skip, limit=limit)


@router.post("/", response_model=models.DeckRead)
async def create_deck(
    deck: models.DeckCreate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await crud.create_deck_for_user(db=db, deck=deck, user_id=user.id)
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="Deck with this slug already exists"
        )
