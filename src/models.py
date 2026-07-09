from enum import Enum
from typing import List, Literal, Optional, Union

from fastapi_users import schemas
from fastapi_users_db_sqlmodel import SQLModelBaseOAuthAccount, SQLModelBaseUserDB
from pydantic import BaseModel
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

# --- Card Element Types ---


class TextElement(BaseModel):
    type: Literal["text"]
    content: str


CardElement = Union[TextElement]


# --- OAuth Account ---


class OAuthAccount(SQLModelBaseOAuthAccount, table=True):
    pass


# --- User DB Model ---


class User(SQLModelBaseUserDB, table=True):
    __tablename__ = "user"

    is_guest: bool = Field(default=False)

    oauth_accounts: List[OAuthAccount] = Relationship(
        sa_relationship_kwargs={"lazy": "joined", "cascade": "all, delete-orphan"}
    )
    decks: List["Deck"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="owner",
    )


# --- User Schemas (Pydantic, not table models) ---


class UserRead(schemas.BaseUser[int]):
    is_guest: bool


class UserCreate(schemas.BaseUserCreate):
    is_guest: bool = False


class UserUpdate(schemas.BaseUserUpdate):
    pass


# --- Deck Models ---


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
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")

    owner: Optional["User"] = Relationship(back_populates="decks")
    cards: List["Card"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="deck",
    )


# --- Card Models ---


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
