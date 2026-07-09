from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from . import crud, models
from .auth.router import create_auth_router, current_active_user
from .database import create_db_and_tables, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

# --- Auth routes ---
app.include_router(create_auth_router(), prefix="/auth")


# --- Deck routes ---


@app.get("/decks/", response_model=List[models.DeckRead])
async def read_my_decks(
    skip: int = 0,
    limit: int = 100,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_decks_for_user(db, user_id=user.id, skip=skip, limit=limit)


@app.post("/decks/", response_model=models.DeckRead)
async def create_deck(
    deck: models.DeckCreate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud.create_deck_for_user(db=db, deck=deck, user_id=user.id)


# --- Card routes ---


@app.get("/decks/{deck_id}/cards/", response_model=List[models.CardRead])
async def read_cards(
    deck_id: int,
    skip: int = 0,
    limit: int = 100,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # TODO: verify that the deck belongs to the user (or is public)
    return await crud.get_cards_for_deck(db, deck_id=deck_id, skip=skip, limit=limit)


@app.post("/decks/{deck_id}/cards/", response_model=models.CardRead)
async def create_card(
    deck_id: int,
    card: models.CardCreate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # TODO: verify that the deck belongs to the user
    return await crud.create_card_for_deck(db=db, card=card, deck_id=deck_id)
