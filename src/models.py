from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


# Element types
class TextElement(BaseModel):
    type: Literal["text"]
    content: str


CardElement = Union[TextElement]


# User Models
class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    is_active: bool = True


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int


class User(UserBase, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str

    decks: List["Deck"] = Relationship(back_populates="owner")


# Deck Models
class PrivacyLevel(str, Enum):
    private = "private"
    unlisted = "unlisted"
    public = "public"


class DeckBase(SQLModel):
    name: str
    slug: str = Field(index=True)
    privacy: PrivacyLevel = Field(default=PrivacyLevel.private)


class DeckCreate(DeckBase):
    pass


class DeckRead(DeckBase):
    id: int
    user_id: int


class Deck(DeckBase, table=True):
    __tablename__ = "decks"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_deck_user_slug"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id")

    owner: Optional[User] = Relationship(back_populates="decks")
    cards: List["Card"] = Relationship(back_populates="deck")


# Card Models
class CardBase(SQLModel):
    front: List[CardElement] = Field(sa_column=Column(JSON))
    back: List[CardElement] = Field(sa_column=Column(JSON))


class CardCreate(CardBase):
    pass


class CardRead(CardBase):
    id: int
    deck_id: int


class Card(CardBase, table=True):
    __tablename__ = "cards"
    id: Optional[int] = Field(default=None, primary_key=True)
    deck_id: Optional[int] = Field(default=None, foreign_key="decks.id")

    deck: Optional[Deck] = Relationship(back_populates="cards")
