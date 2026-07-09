from typing import List

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Session, SQLModel

from . import crud, models
from .database import engine, get_db

SQLModel.metadata.create_all(engine)

app = FastAPI()


@app.post("/users/", response_model=models.UserRead)
def create_user(user: models.UserCreate, db: Session = Depends(get_db)):
    if user.email:
        db_user = crud.get_user_by_email(db, email=user.email)
        if db_user:
            raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)


@app.get("/users/", response_model=List[models.UserRead])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = crud.get_users(db, skip=skip, limit=limit)
    return users


@app.get("/users/{user_id}", response_model=models.UserRead)
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@app.post("/users/{user_id}/decks/", response_model=models.DeckRead)
def create_deck_for_user(
    user_id: int, deck: models.DeckCreate, db: Session = Depends(get_db)
):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.create_deck_for_user(db=db, deck=deck, user_id=user_id)


@app.get("/decks/", response_model=List[models.DeckRead])
def read_decks(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    decks = crud.get_decks(db, skip=skip, limit=limit)
    return decks


@app.post("/decks/{deck_id}/cards/", response_model=models.CardRead)
def create_card_for_deck(
    deck_id: int, card: models.CardCreate, db: Session = Depends(get_db)
):
    return crud.create_card_for_deck(db=db, card=card, deck_id=deck_id)
