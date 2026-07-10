from typing import List

import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..database import get_db

router = APIRouter(prefix="/decks", tags=["decks"])


@router.post("/", response_model=models.DeckRead)
async def create_deck(
    deck: models.DeckCreate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if deck.folder_id is not None:
        folder = await crud.get_folder(db, folder_id=deck.folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        if folder.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not enough permissions")

    try:
        return await crud.create_deck_for_user(db=db, deck=deck, user_id=user.id)
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="Deck with this slug already exists"
        )
