from sqlmodel import Session, select

from . import models


# User
def get_user(db: Session, user_id: int):
    return db.get(models.User, user_id)


def get_user_by_email(db: Session, email: str):
    statement = select(models.User).where(models.User.email == email)
    return db.exec(statement).first()


def get_users(db: Session, skip: int = 0, limit: int = 100):
    statement = select(models.User).offset(skip).limit(limit)
    return db.exec(statement).all()


def create_user(db: Session, user: models.UserCreate):
    fake_hashed_password = (
        (user.password + "notreallyhashed") if user.password else None
    )
    db_user = models.User(
        **user.model_dump(exclude={"password"}), hashed_password=fake_hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# Deck
def get_decks(db: Session, skip: int = 0, limit: int = 100):
    statement = select(models.Deck).offset(skip).limit(limit)
    return db.exec(statement).all()


def create_deck_for_user(db: Session, deck: models.DeckCreate, user_id: int):
    db_deck = models.Deck(**deck.model_dump(), user_id=user_id)
    db.add(db_deck)
    db.commit()
    db.refresh(db_deck)
    return db_deck


# Card
def create_card_for_deck(db: Session, card: models.CardCreate, deck_id: int):
    db_card = models.Card(**card.model_dump(), deck_id=deck_id)
    db.add(db_card)
    db.commit()
    db.refresh(db_card)
    return db_card
